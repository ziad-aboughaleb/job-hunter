import logging
import time

import httpx

from jobhunter.core.logger import console
from jobhunter.core.paths import DATA_PATH, read, write
from jobhunter.core.settings import settings
from jobhunter.core.textutil import clean_html
from jobhunter.models import EvaluatedCandidate

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
  """Updates seen.json with sent UIDs and purges sent candidates from candidates.json and evaluated.json."""
  logger.info("Updating state files (seen.json, candidates.json, evaluated.json)...")
  console.print("[dim cyan]Updating local state files...[/dim cyan]")

  sent_uids = {c.uid for c in sent_candidates}
  if not sent_uids:
    return

  seen_data = read(DATA_PATH / "seen.json", dict)

  for uid in sent_uids:
    seen_data[uid] = True
  write(DATA_PATH / "seen.json", seen_data)

  candidates = read(DATA_PATH / "candidates.json", list)
  filtered_candidates = [c for c in candidates if c.get("uid") not in sent_uids]
  write(DATA_PATH / "candidates.json", filtered_candidates)

  evaluated = read(DATA_PATH / "evaluated.json", list)
  filtered_evaluated = [e for e in evaluated if e.get("uid") not in sent_uids]
  write(DATA_PATH / "evaluated.json", filtered_evaluated)

  logger.info(f"Successfully cleaned up state for {len(sent_uids)} sent candidates.")


def main(dry_run: bool = False):
  """Orchestrates the Telegram notification pipeline."""
  logger.info("Starting Telegram send pipeline run.")
  console.print("[bold cyan]Dispatching job evaluations to Telegram...[/bold cyan]")

  tasks = build_send_tasks()
  if not tasks:
    logger.warning("No new passing candidates found to send.")
    console.print("[yellow]No pending job alerts to send.[/yellow]")
    return

  sent_candidates, failed_count = execute_telegram_sends(tasks)

  if sent_candidates and not dry_run:
    save_send_results(sent_candidates)
  elif dry_run:
    logger.info("Dry run enabled. Skipping state file updates.")
    console.print("\n[yellow]Dry run mode: skipped saving to local state files.[/yellow]")

  total_sent = len(sent_candidates)
  logger.info(f"Pipeline finished. Sent: {total_sent} | Failed: {failed_count}")

  console.print("\n[bold]Telegram Dispatch Summary[/bold]")
  console.print("───────────────────────────────────────")
  console.print(f"Alerts sent     : [bold green]{total_sent}[/bold green]")
  console.print(f"Failed deliveries: [red]{failed_count}[/red]")
  console.print(f"Dry run mode    : [yellow]{dry_run}[/yellow]")
  console.print("───────────────────────────────────────\n")
