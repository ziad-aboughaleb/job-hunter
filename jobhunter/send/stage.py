"""Stage 3: check the model's results, send the matches to Telegram, and remember what is finished.

    run()   the `send` command (also `send --check`, `--dry-run` and `--test`)

The decisions (which jobs match, which are finished) live in matches.py; the Telegram details live in telegram.py.
"""
import html
import json
import os
import re
import sys
import time
from typing import List, Set, Tuple

from jobhunter.helpers import store
from jobhunter.helpers.config import load_config, load_env
from jobhunter.send import telegram
from jobhunter.send.matches import load_results, record_seen, select_matches


def _plain(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text))


def run(dry_run: bool = False, check_only: bool = False, test: bool = False) -> int:
    """The `send` command. Returns the process exit code."""
    load_env()
    cfg = load_config()
    token, chat_id = os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "")
    preview = cfg["telegram"]["link_preview"]

    if not (dry_run or check_only) and not (token and chat_id):
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID are missing. Run `python -m jobhunter init` (or copy examples/.env.example to .env) and fill it in.",
              file=sys.stderr)
        return 1

    def notify(text: str) -> Tuple[bool, str]:
        if dry_run:
            print("-" * 60 + "\n" + _plain(text) + "\n")
            return True, ""
        return telegram.send_message(token, chat_id, text, preview)

    if test:
        ok, error = telegram.send_message(token, chat_id, "✅ <b>Job hunter</b>: Telegram connection works.", preview)
        print("Test message sent." if ok else f"Failed: {error}")
        return 0 if ok else 1

    # ---- load what the earlier stages wrote ----
    try:
        candidates = store.read_data("candidates.json", None)
    except json.JSONDecodeError:
        candidates = None
    status = store.read_data("run_status.json", {}) or {}

    if candidates is None:
        message = "⚠️ <b>Job scan failed</b>: data/candidates.json is missing, so the fetch step did not run or crashed."
        print(_plain(message), file=sys.stderr)
        if not check_only:
            notify(message)
        return 1

    errors = status.get("errors", [])
    header = f"Fetched {status.get('fetched', '?')} jobs from {status.get('sources_ok', '?')}/{status.get('sources_total', '?')} sources"

    if not candidates:
        print("No candidates today.")
        if not check_only and cfg["telegram"]["notify_on_empty"]:
            extra = f"\n⚠️ {len(errors)} source(s) failed: {telegram.escape('; '.join(errors[:3]), 300)}" if errors else ""
            notify(f"📭 <b>Job scan</b>: no new jobs passed the filters.\n{telegram.escape(header)}{extra}")
        return 0

    results, problems = load_results(candidates)
    for problem in problems:
        print(f"  ! {problem}", file=sys.stderr)
    if check_only:
        print("results.json looks valid." if not problems else f"{len(problems)} problem(s) found.")
        return 1 if problems else 0

    # ---- send the matches ----
    by_ref = {c["ref"]: c for c in candidates}
    threshold = cfg["score_threshold"]
    to_send, deferred = select_matches(results, threshold, cfg["limits"]["max_messages"])
    matches = len(to_send) + len(deferred)

    sent: Set[str] = set()
    failures: List[str] = []
    for result in to_send:
        ok, error = notify(telegram.format_card(by_ref[result["ref"]], result))
        if ok:
            sent.add(result["ref"])
        else:
            failures.append(f"{result['ref']}: {error}")
            print(f"  ! Telegram send failed for {result['ref']}: {error}", file=sys.stderr)
        time.sleep(0 if dry_run else 1)

    if not dry_run:
        record_seen(candidates, results, sent, threshold, cfg["limits"]["seen_retention_days"])

    # ---- one summary message ----
    summary = [
        "📊 <b>Job scan</b>",
        telegram.escape(header),
        f"Passed filters: {len(candidates)} · evaluated: {len(results)} · matches ≥{threshold}%: {matches} · sent: {len(sent)}",
    ]
    if not matches:
        summary.append("No strong matches today.")
    if deferred:
        summary.append(f"⏭ {len(deferred)} more match(es) held back by the message cap; they are sent next run.")
    warnings = list(problems) + failures
    if errors:
        warnings.append(f"{len(errors)} source(s) failed to load")
    if warnings:
        summary.append("⚠️ " + telegram.escape("; ".join(warnings), 600))
    notify("\n".join(summary))

    return 1 if (failures or problems) else 0
