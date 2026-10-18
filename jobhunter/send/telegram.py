"""Telegram: formatting a job as a message, and sending it.

Telegram's HTML mode is strict, so EVERYTHING that comes from a job posting or from the model goes
through escape() first. Messages are also limited to 4096 characters, which the length limits below respect.
"""
import html
from typing import Any, Dict, Tuple

from jobhunter.helpers import http


def escape(value: Any, limit: int = 0) -> str:
    """Make text safe for Telegram's HTML mode, shortening it to `limit` characters if given."""
    text = str(value or "").strip()
    if limit and len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return html.escape(text, quote=False)


def format_card(job: Dict[str, Any], result: Dict[str, Any]) -> str:
    """One matching job as a Telegram message. `job` is a candidates.json record, `result` a normalized result."""
    star = "⭐ " if job.get("priority") else ""
    link = html.escape(job["url"], quote=True)
    lines = [
        f'{star}🟢 <b><a href="{link}">{escape(job["title"], 120)} — {escape(job["company"], 60)}</a></b>',
        f'• <b>Match Score:</b> {result["score"]}%',
        f'• <b>Location:</b> {escape(job["location"] or "Remote", 120)}',
    ]
    if job.get("posted"):
        lines.append(f'• <b>Posted:</b> {escape(job["posted"])}')
    lines += ["", "<b>Why It Matches:</b>"]
    lines += [f"• {escape(item, 250)}" for item in result["strengths"][:3]] or ["• (none listed)"]
    lines += ["", "<b>Skill Gaps:</b>"]
    lines += [f"• {escape(item, 250)}" for item in result["gaps"][:3]] or ["• None"]
    if result["pitch"]:
        lines += ["", "<b>Tailored Pitch Line:</b>", f'<i>"{escape(result["pitch"], 400)}"</i>']
    return "\n".join(lines)


def send_message(token: str, chat_id: str, text: str, preview: bool = False) -> Tuple[bool, str]:
    """Send one message. Returns (ok, error_text). Never raises, and never leaks the bot token in errors."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": not preview}
    try:
        http.post_json(url, payload, timeout=20)
        return True, ""
    except http.HttpStatusError as exc:
        return False, str(exc).replace(token, "***")
    except http.NetworkError as exc:
        return False, str(exc).replace(token, "***")
