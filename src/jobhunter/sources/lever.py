import logging
import re
from datetime import UTC, datetime

from jobhunter.core.http import fetch_url
from jobhunter.core.logger import console
from jobhunter.core.textutil import clean_html, parse_date
from jobhunter.models import Job
from jobhunter.sources.base import BaseSource

logger = logging.getLogger(__name__)


class Source(BaseSource):
  name = "lever"
  domains = ["lever.co"]
  url_patterns = [re.compile(r"lever\.co/(?P<slug>[^/]+)")]

  def fetch(self, slug: str = "", skip_parsing: bool = False, **kwargs) -> list[Job]:
    """Fetches job listings from a specific company's Lever API."""
    if not slug:
      raise ValueError(f"A company slug must be provided to fetch {self.name} jobs.")

    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    data = fetch_url(url, expected_type=list)

    if skip_parsing:
      return []

    jobs: list[Job] = []

    for item in data:
      if not isinstance(item, dict):
        logger.warning(f"[ {self.name} ] Skipping unexpected item format: {type(item).__name__}")
        console.print(f"  [yellow]⚠ [ {self.name} ] Skipping unexpected item format...[/yellow]")
        continue

      job_id = str(item.get("id") or "")
      title = str(item.get("text") or "")
      job_url = str(item.get("hostedUrl") or "")

      if not all([job_id, title, job_url]):
        logger.warning(f"[ {self.name} ] Skipping item with missing required fields: {item}")
        console.print(f"  [yellow]⚠ [ {self.name} ] Skipping item with missing required fields.[/yellow]")
        continue

      try:
        categories = item.get("categories") or {}
        location = categories.get("location") or ", ".join(categories.get("allLocations") or [])

        parts = [item.get("descriptionPlain") or ""]
        for block in item.get("lists") or []:
          block_text = block.get("text") or ""
          block_content = clean_html(block.get("content") or "")
          parts.append(f"{block_text}\n{block_content}")
        parts.append(item.get("additionalPlain") or "")

        is_remote = str(item.get("workplaceType", "")).lower() == "remote"

        created_raw = item.get("createdAt")
        posted = datetime.fromtimestamp(created_raw / 1000, tz=UTC).strftime("%Y-%m-%d") if isinstance(created_raw, (int, float)) else parse_date(str(created_raw) if created_raw else None)

        jobs.append(
          Job(
            source=self.name,
            board=slug,
            company=slug.replace("-", " ").title(),
            job_id=job_id,
            title=title,
            url=job_url,
            location=location or "",
            remote=True if is_remote else None,
            posted=posted,
            description="\n\n".join(p for p in parts if p).strip(),
          )
        )

      except Exception as e:
        logger.exception(f"[ {self.name} ] Error parsing job '{job_id}' for '{slug}': {e}")
        console.print(f"  [red]✖ [ {self.name} ] Error parsing job '{job_id}'[/red]")
        continue

    return jobs
