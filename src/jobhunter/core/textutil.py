import html
import re
from datetime import datetime


def clean_html(text: str | None) -> str:
  """Cleans HTML content by unescaping entities, removing tags, and normalizing whitespace."""
  if not text:
    return ""

  text = html.unescape(text)
  text = re.sub(r"<[^>]+>", " ", text)
  text = re.sub(r"\s+", " ", text)

  return text.strip()


def parse_date(date_str: str | None) -> str:
  """Parses a date string into a standard ISO 8601 format."""
  if not date_str:
    return ""

  try:
    clean_date_str = date_str.replace("Z", "+00:00")
    dt = datetime.fromisoformat(clean_date_str)
    return dt.strftime("%Y-%m-%d")

  except ValueError:
    return date_str.strip()
