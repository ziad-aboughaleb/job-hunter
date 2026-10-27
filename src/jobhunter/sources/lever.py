import re
from datetime import UTC, datetime

import httpx

from jobhunter.core.http import fetch_json
from jobhunter.core.logger import get_logger
from jobhunter.core.textutil import clean_html, parse_date
from jobhunter.models import Job
from jobhunter.sources.base import BaseSource

logger = get_logger(__name__)


class Source(BaseSource):
  name = "lever"
  domains = ["lever.co"]
  url_patterns = [re.compile(r"lever\.co/(?P<slug>[^/]+)")]

  def fetch(self, slug: str = "", **kwargs) -> list[Job]:
    """Fetches job listings from a specific company's Lever API."""
    if not slug:
      raise ValueError(f"A company slug must be provided to fetch {self.name} jobs.")

    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"

    try:
      data = fetch_json(url, expected_type=list)
    except httpx.HTTPStatusError:
      raise
    except (httpx.HTTPError, ValueError) as e:
      raise RuntimeError(f"Failed to fetch {self.name} jobs for {slug}: {e}") from e

    if not isinstance(data, list):
      return []

    jobs = []

    for item in data:
      if not isinstance(item, dict):
        logger.warning(f"Skipping unexpected item format from {self.name}: {type(item)}")
        continue

      job_id = str(item.get("id") or "")
      title = str(item.get("text") or "")
      job_url = str(item.get("hostedUrl") or "")

      if not all([job_id, title, job_url]):
        logger.warning(f"Skipping {self.name} item with missing required fields: {item}")
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
        posted = datetime.fromtimestamp(created_raw / 1000, tz=UTC).isoformat() if isinstance(created_raw, int) else parse_date(created_raw)

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
        logger.error(f"Error parsing {self.name} job {job_id}: {e}")
        continue

    return jobs
