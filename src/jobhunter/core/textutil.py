import html
import re
from datetime import datetime


def clean_html(text: str | None) -> str:
  """Cleans HTML content, normalizes whitespace, and escapes <, >, & for safe HTML/XML embedding."""
  if not text:
    return ""

  # 1. Remove script and style blocks with their contents
  text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.DOTALL | re.IGNORECASE)

  # 2. Strip real HTML/XML tags (ignores math comparisons like "< 2 years and > 1")
  text = re.sub(r"<[/!?a-zA-Z][^>]*>", " ", text)

  # 3. Unescape entities
  text = html.unescape(text)

  # 4. Strip any tags that were hidden as entities (e.g. &lt;/job&gt;)
  text = re.sub(r"<[/!?a-zA-Z][^>]*>", " ", text)

  # 5. Normalize whitespace
  text = re.sub(r"\s+", " ", text).strip()

  # 6. Escape <, >, & for safe Telegram HTML and XML prompts
  return html.escape(text, quote=False)


def parse_date(date_str: str | None) -> str:
  """Parses an ISO date string into YYYY-MM-DD format."""
  if not date_str:
    return ""

  try:
    dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    return dt.strftime("%Y-%m-%d")
  except ValueError:
    return date_str.strip()
