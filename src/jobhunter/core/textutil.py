import html
import re
from datetime import datetime


def clean_html(text: str | None) -> str:
  """Cleans HTML content by removing tags, unescaping entities, and normalizing whitespace."""
  if not text:
    return ""

  # 1. Remove script and style blocks with their contents
  text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.DOTALL | re.IGNORECASE)

  # 2. Strip HTML tags
  text = re.sub(r"<[^>]+>", " ", text)

  # 3. Unescape entities after tags are gone
  text = html.unescape(text)

  # 4. Normalize whitespace
  return re.sub(r"\s+", " ", text).strip()


def parse_date(date_str: str | None) -> str:
  """Parses an ISO date string into YYYY-MM-DD format."""
  if not date_str:
    return ""

  try:
    dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    return dt.strftime("%Y-%m-%d")
  except ValueError:
    return date_str.strip()
