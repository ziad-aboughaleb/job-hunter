import logging
import time

import httpx

from jobhunter.core.logger import console
from jobhunter.core.paths import DATA_PATH, read, write
from jobhunter.core.settings import settings
from jobhunter.core.status import save_status, start_stage
from jobhunter.core.textutil import clean_html
from jobhunter.models import EvaluatedCandidate, HistoryEntry

logger = logging.getLogger(__name__)


def build_send_tasks() -> list[EvaluatedCandidate]:
  """Loads all evaluated candidates from disk and filters for jobs that passed evaluation (no score floor)."""
  logger.info("Building send tasks...")

  raw_evals = read(DATA_PATH / "evaluated.json", list)

  tasks = []
  for item in raw_evals:
    try:
      evaluation = item.get("evaluation", {})
      hard_fail = evaluation.get("hard_fail", True)

      if not hard_fail:
        eval_candidate = EvaluatedCandidate(**item)
        tasks.append(eval_candidate)

    except Exception as e:
      logger.error(f"Failed to parse evaluated candidate {item.get('uid', 'unknown')}: {e}")
      console.print(f"  [red]✖ Failed to parse evaluated candidate {item.get('uid', 'unknown')}[/red]")

  logger.info(f"Generated {len(tasks)} send tasks from evaluated candidates.")

  return tasks


def send_single_telegram_message(candidate: EvaluatedCandidate) -> bool:
  token = settings.telegram_bot_token
  chat_id = settings.telegram_chat_id
  eval_data = candidate.evaluation

  priority_badge = "⭐ <b>[VIP COMPANY]</b> " if candidate.priority else ""

  score_threshold = settings.evaluating.score_threshold
  if eval_data.score >= 80:
    score_emoji = "🟢"
  elif eval_data.score >= score_threshold:
    score_emoji = "🟡"
  else:
    score_emoji = "🟠"

  pitch_section = f"\n💡 <b>Pitch:</b>\n{clean_html(eval_data.pitch)}\n" if eval_data.pitch else ""

  message = f"""
🎯 <b>New Job Match!</b>
{priority_badge}({score_emoji} Score: <code>{eval_data.score}/100</code>)

🏢 <b>Company:</b> {clean_html(candidate.company)}
💼 <b>Title:</b> {clean_html(candidate.title)}
📍 <b>Location:</b> {clean_html(candidate.location) or "Remote"}

🔍 <b>Reasoning:</b>\n{clean_html(eval_data.reasoning)}
📈 <b>Score Breakdown:</b>\n{clean_html(eval_data.score_explanation)}
{pitch_section}
🔗 <a href="{candidate.url}">View Job Posting</a>
"""

  url = f"https://api.telegram.org/bot{token}/sendMessage"
  payload = {
    "chat_id": chat_id,
    "text": message,
    "parse_mode": "HTML",
    "disable_web_page_preview": True,
  }

  try:
    response = httpx.post(url, json=payload, timeout=10.0)
    response.raise_for_status()
    return True
  except httpx.HTTPStatusError as e:
    logger.exception(f"Telegram API Error ({e.response.status_code}) for {candidate.company}: {e.response.text}")
    console.print(f"  [red]✖ Telegram API Error: {e.response.status_code}[/red]")
    return False
  except Exception as e:
    logger.exception(f"Failed to send Telegram notification for {candidate.company}: {e}")
    console.print(f"  [red]✖ Failed to send Telegram notification for {candidate.company}[/red]")
    return False


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

    time.sleep(1)

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
  retention_cutoff = current_time - (settings.limits.seen_retention_days * 86400)
  seen_data = {uid: ts for uid, ts in seen_data.items() if ts > retention_cutoff}
  seen_data = dict(sorted(seen_data.items(), key=lambda item: item[1], reverse=True))
  write(DATA_PATH / "seen.json", seen_data)

  history_data = read(DATA_PATH / "history.json", dict)
  for item in all_evaluated:
    uid = item.get("uid")
    if uid in seen_data:
      eval_cand = EvaluatedCandidate(**item)
      entry = HistoryEntry.from_evaluated(
        eval_cand,
        passed=not eval_cand.evaluation.hard_fail,
      )
      history_data[uid] = entry.model_dump(mode="json")
  history_data = {uid: rec for uid, rec in history_data.items() if uid in seen_data}
  history_data = dict(sorted(history_data.items(), key=lambda item: item[1].get("recorded_at", ""), reverse=True))
  write(DATA_PATH / "history.json", history_data)

  candidates = read(DATA_PATH / "candidates.json", list)
  filtered_candidates = [c for c in candidates if c.get("uid") not in all_evaluated_uids]
  write(DATA_PATH / "candidates.json", filtered_candidates)

  failed_to_send = [e for e in all_evaluated if e.get("uid") not in sent_uids and not e.get("evaluation", {}).get("hard_fail", True)]
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
