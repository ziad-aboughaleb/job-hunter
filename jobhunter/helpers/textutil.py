"""Small text helpers shared by the sources and the filters."""
import html
import re
from datetime import datetime, timezone
from typing import Optional


def clean_html(raw: Optional[str]) -> str:
    """Turn a job description (HTML, or HTML-escaped HTML) into plain text, keeping line breaks."""
    text = html.unescape(raw or "")  # Greenhouse sends HTML that has itself been HTML-escaped
    text = re.sub(r"(?i)<\s*(br|/p|/div|/li|/h[1-6]|/ul|/ol)\s*/?>", "\n", text)  # block ends -> newline
    text = re.sub(r"(?i)<li[^>]*>", "- ", text)  # list items -> "- "
    text = re.sub(r"<[^>]+>", " ", text)  # drop every other tag
    text = html.unescape(text)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)  # no stray spaces around line breaks
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def parse_date(value) -> Optional[datetime]:
    """Understand the date formats the job sites use. Returns a timezone-aware datetime, or None.

    Handles ISO strings, '2026-07-27 14:23:51 UTC', '+0000' offsets, date-only values,
    and epoch milliseconds (an int).
    """
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        text = str(value).strip()
        text = re.sub(r"\s*UTC$", "+00:00", text)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        text = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", text)  # +0000 -> +00:00
        fraction = re.search(r"\.(\d+)", text)
        if fraction:  # older Pythons need exactly 3 or 6 fractional digits
            text = text.replace(fraction.group(0), "." + (fraction.group(1) + "000000")[:6], 1)
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (ValueError, OSError, OverflowError):
        return None


def term_in(text: str, term: str) -> bool:
    """Whole-word, case-insensitive match of `term` inside `text`.

    Whole words matter: "java" must not match "JavaScript", "usa" must not match "Lusaka",
    and "ios" must not match "Studios". Terms that start or end with punctuation
    (".net", "c++", "u.s.") skip the boundary check on that side.
    """
    needle = term.strip().lower()
    if not needle:
        return False
    before = r"(?<!\w)" if needle[0].isalnum() else ""
    after = r"(?!\w)" if needle[-1].isalnum() else ""
    return re.search(before + re.escape(needle) + after, text.lower()) is not None


def pretty_company(slug: str) -> str:
    """'acme-corp' -> 'Acme Corp' (used when a source does not give a company name)."""
    return slug.replace("-", " ").replace("_", " ").title()
