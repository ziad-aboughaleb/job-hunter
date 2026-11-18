import logging
import time

import httpx
from jobhunter.core.logger import console
from jobhunter.core.paths import DATA_PATH, read, write
from jobhunter.core.settings import settings
from jobhunter.core.status import save_status, start_stage
from jobhunter.core.textutil import clean_html
from jobhunter.models import EvaluatedCandidate, HistoryEntry, RunStatus

logger = logging.getLogger(__name__)


def _is_sendable(evaluation: dict) -> bool:
  if evaluation.get("hard_fail", True):
    return False
  if settings.telegram.send_low_scores:
    return True
  return evaluation.get("score", 0) >= settings.evaluating.score_threshold


def _post_telegram(text: str, silent: bool = False) -> bool:
  token, chat_id = settings.telegram_bot_token, settings.telegram_chat_id
  if not token or not chat_id:
    logger.error("Telegram token or chat ID is missing in settings.")
    return False

  try:
    response = httpx.post(
      f"https://api.telegram.org/bot{token}/sendMessage",
      json={
        "chat_id": chat_id,
        "text": text.strip(),
        "parse_mode": "HTML",
        "disable_web_page_preview": not settings.telegram.link_preview,
        "disable_notification": silent,
      },
      timeout=10.0,
    )
    response.raise_for_status()
    return True
  except httpx.HTTPStatusError as e:
    logger.exception(f"Telegram API Error ({e.response.status_code}): {e.response.text}")
  except Exception as e:
    logger.exception(f"Telegram request failed: {e}")
  return False


def build_send_tasks() -> list[EvaluatedCandidate]:
  """Loads all evaluated candidates from disk and filters for jobs that passed evaluation (no score floor)."""
  logger.info("Building send tasks...")

  raw_evals = read(DATA_PATH / "evaluated.json", list)

  tasks = []
  for item in raw_evals:
    try:
      if _is_sendable(item.get("evaluation", {})):
        eval_candidate = EvaluatedCandidate(**item)
        tasks.append(eval_candidate)

    except Exception as e:
      logger.error(f"Failed to parse evaluated candidate {item.get('uid', 'unknown')}: {e}")
      console.print(f"  [red]✖ Failed to parse evaluated candidate {item.get('uid', 'unknown')}[/red]")

  logger.info(f"Generated {len(tasks)} send tasks from evaluated candidates.")

  return tasks


def send_single_telegram_message(candidate: EvaluatedCandidate) -> bool:
  eval_data = candidate.evaluation

  priority_badge = "✦\ufe0e <b>VIP</b> · " if candidate.priority else ""

  score_threshold = settings.evaluating.score_threshold
  low_band = settings.evaluating.low_band
  if eval_data.score >= score_threshold:
    score_dot = "🟢"
  elif eval_data.score >= low_band:
    score_dot = "🟡"
  else:
    score_dot = "🟠"

  message = f"""
<b>{clean_html(candidate.title)}</b>
{priority_badge}{score_dot} <code>{eval_data.score}/100</code>

- <b>Company:</b> {clean_html(candidate.company)}
- <b>Location:</b> {clean_html(candidate.location) or "Remote"}

<blockquote expandable><b>Reasoning</b>
{clean_html(eval_data.reasoning)}</blockquote>

<blockquote expandable><b>Score Breakdown</b>
{clean_html(eval_data.score_explanation)}</blockquote>

↗\ufe0e <a href="{candidate.url}">View Job Posting</a>
"""

  return _post_telegram(message)


def send_run_summary() -> None:
  """Sends a concise pipeline summary to Telegram when notable activity, errors, or notify_on_empty is enabled."""
  raw_status = read(DATA_PATH / "runstatus.json", dict)
  if not raw_status:
    return

  try:
    status = RunStatus(**raw_status)
  except Exception as e:
    logger.warning(f"Could not parse status.json for Telegram summary: {e}")
    return

  if status.error == "Aborted by user":
    return

  m = status.metrics
  has_failure = status.status == "failed" or m.eval_errors > 0 or m.send_failed > 0
  has_activity = m.sent_count > 0

  if not has_failure and not has_activity and not settings.telegram.notify_on_empty:
    logger.info("Pipeline run had no new activity or errors; skipping Telegram summary.")
    return

  end_time = status.finished_at or status.updated_at
  duration_sec = max(0, int((end_time - status.started_at).total_seconds()))
  duration_str = f"{duration_sec // 60}m {duration_sec % 60}s" if duration_sec >= 60 else f"{duration_sec}s"

  if status.status == "failed":
    header = f"🔴 <b>Pipeline Failed</b> · <code>{status.current_stage} · {duration_str}</code>"
  elif has_failure:
    header = f"🟡 <b>Pipeline Completed with Errors</b> · <code>{duration_str}</code>"
  else:
    header = f"🟢 <b>Pipeline Summary</b> · <code>{duration_str}</code>"

  skipped_total = m.skipped_seen + m.skipped_dupes + m.skipped_filters + m.cut_over_cap
  if settings.telegram.send_low_scores:
    passed_total = m.eval_passed + m.low_score
    rejected_total = m.hard_failed
  else:
    passed_total = m.eval_passed
    rejected_total = m.hard_failed + m.low_score

  error_block = f"\n- <b>Error:</b> <code>{clean_html(status.error[:200])}</code>\n" if status.error else ""

  message = f"""
{header}
{error_block}
- <b>Fetched:</b> {m.new_candidates} new ({skipped_total} skipped)
- <b>Evaluated:</b> {passed_total} passed · {rejected_total} rejected
- <b>Sent:</b> {m.sent_count} alerts

<blockquote expandable><b>Full Breakdown</b>
Total scraped: {m.fetched_total} (seen: {m.skipped_seen}, dupes: {m.skipped_dupes}, filtered: {m.skipped_filters}, cap: {m.cut_over_cap})
Evaluated: {m.evaluated_count} (hard fails: {m.hard_failed}, low score: {m.low_score}, errors: {m.eval_errors})
Delivery: {m.sent_count} sent, {m.send_failed} failed</blockquote>
"""

  _post_telegram(message, silent=not has_failure)


def execute_telegram_sends(tasks: list[EvaluatedCandidate]) -> tuple[list[EvaluatedCandidate], int]:
  """Iterates through send tasks and dispatches notifications via Telegram."""
  logger.info(f"Executing Telegram dispatch across {len(tasks)} candidates.")
  console.print(f"[bold cyan]Sending {len(tasks)} job alerts via Telegram...[/bold cyan]")

  token = settings.telegram_bot_token
  chat_id = settings.telegram_chat_id

  if not token or not chat_id:
    logger.error("Telegram token or chat ID is missing in settings.")
    console.print("[bold red]Error: Telegram token or chat ID not configured in settings.[/bold red]")
    return [], 0

  sent_candidates = []
  failed_count = 0

  for candidate in tasks:
    success = send_single_telegram_message(candidate)

    if success:
      sent_candidates.append(candidate)
      console.print(f"  [green]✔ Sent alert for {candidate.company} - {candidate.title}[/green]")
    else:
      failed_count += 1
      console.print(f"  [red]✖ Failed to send alert for {candidate.company}[/red]")

    if settings.telegram.message_delay > 0:
      time.sleep(settings.telegram.message_delay)

  logger.info(f"Telegram dispatch complete. Successfully sent: {len(sent_candidates)}, Failed: {failed_count}")

  return sent_candidates, failed_count


def save_send_results(sent_candidates: list[EvaluatedCandidate]):
  """Logs evaluated jobs to seen.json, then purges them from state files."""
  logger.info("Updating state files...")
  console.print("[dim cyan]Updating local state files...[/dim cyan]")

  all_evaluated = read(DATA_PATH / "evaluated.json", list)
  if not all_evaluated:
    return

  all_evaluated_uids = {e.get("uid") for e in all_evaluated if e.get("uid")}
  sent_uids = {c.uid for c in sent_candidates}
  current_time = int(time.time())

  seen_data = read(DATA_PATH / "seen.json", dict)
  for uid in all_evaluated_uids:
    seen_data[uid] = current_time
  cutoff = current_time - (settings.limits.seen_retention_days * 86400)
  seen_data = dict(sorted(((u, ts) for u, ts in seen_data.items() if ts > cutoff), key=lambda x: x[1], reverse=True))
  write(DATA_PATH / "seen.json", seen_data)

  history_data = read(DATA_PATH / "history.json", list)
  new_entries = [HistoryEntry.from_evaluated(EvaluatedCandidate(**item)).model_dump(mode="json") for item in all_evaluated if item.get("uid") in seen_data]
  existing = [rec for rec in history_data if rec.get("uid") in seen_data and rec.get("uid") not in all_evaluated_uids]
  write(DATA_PATH / "history.json", new_entries + existing)

  candidates = read(DATA_PATH / "candidates.json", list)
  filtered_candidates = [c for c in candidates if c.get("uid") not in all_evaluated_uids]
  write(DATA_PATH / "candidates.json", filtered_candidates)

  failed_to_send = [e for e in all_evaluated if e.get("uid") not in sent_uids and _is_sendable(e.get("evaluation", {}))]
  write(DATA_PATH / "evaluated.json", failed_to_send)


def main(dry_run: bool = False, complete_on_exit: bool = True):
  """Orchestrates the Telegram notification pipeline."""
  status = start_stage("send")
  try:
    logger.info("Starting Telegram send pipeline run.")
    console.print("[bold cyan]Dispatching job evaluations to Telegram...[/bold cyan]")

    all_evaluated = read(DATA_PATH / "evaluated.json", list)
    if not all_evaluated:
      logger.info("No evaluated candidates exist.")
      console.print("[yellow]No evaluated jobs pending processing.[/yellow]")
      if complete_on_exit:
        status.mark_completed()
      save_status(status)
      return

    tasks = build_send_tasks()

    sent_candidates = []
    failed_count = 0

    if tasks:
      sent_candidates, failed_count = execute_telegram_sends(tasks)
    else:
      logger.info("No pending job alerts to send (all evaluated jobs hard-failed).")
      console.print("[dim]No passing jobs to alert you about. Updating seen state...[/dim]")

    if not dry_run:
      save_send_results(sent_candidates)
    else:
      logger.info("Dry run enabled. Skipping state file updates.")
      console.print("\n[yellow]Dry run mode: skipped saving to local state files.[/yellow]")

    total_sent = len(sent_candidates)
    logger.info(f"Pipeline finished. Sent: {total_sent} | Failed: {failed_count}")

    console.print("\n[bold]Telegram Dispatch Summary[/bold]")
    console.print("───────────────────────────────────────")
    console.print(f"Alerts sent       : [bold green]{total_sent}[/bold green]")
    console.print(f"Failed deliveries : [red]{failed_count}[/red]")
    console.print(f"Dry run mode      : [yellow]{dry_run}[/yellow]")
    console.print("───────────────────────────────────────\n")

    status.metrics.sent_count = total_sent
    status.metrics.send_failed = failed_count

    if complete_on_exit:
      status.mark_completed()
    save_status(status)

  except KeyboardInterrupt:
    status.mark_failed("Aborted by user")
    save_status(status)
    raise
  except Exception as e:
    status.mark_failed(str(e))
    save_status(status)
    raise
