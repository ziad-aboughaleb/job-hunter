import logging
import time
from datetime import UTC, datetime

import httpx

from jobhunter.core.http import fetch_json
from jobhunter.core.textutil import clean_html, parse_date
from jobhunter.models import Job
from jobhunter.sources.base import BaseSource

logger = logging.getLogger(__name__)


class Source(BaseSource):
  name = "arbeitnow"
  domains = ["arbeitnow.com"]
  is_aggregator = True

  def fetch(self, slug: str = "", **kwargs) -> list[Job]:
    """Fetches all available job listings from the Arbeitnow API via pagination link traversal."""
    url = "https://www.arbeitnow.com/api/job-board-api"

    jobs = []

    while url:
      try:
        data = fetch_json(url, expected_type=dict)
      except httpx.HTTPStatusError:
        raise
      except (httpx.HTTPError, ValueError) as e:
        raise RuntimeError(f"Failed to fetch {self.name} jobs from {url}: {e}") from e

      if not isinstance(data, dict):
        return []

      for item in data.get("data", []):
        if not isinstance(item, dict):
          logger.warning(f"Skipping unexpected item format from {self.name}: {type(item)}")
          continue

        job_id = str(item.get("slug") or "")
        title = str(item.get("title") or "")
        job_url = str(item.get("url") or "")

        if not all([job_id, title, job_url]):
          logger.warning(f"Skipping {self.name} item with missing required fields: {item}")
          continue

        try:
          tags = ", ".join(item.get("tags") or [])
          description = item.get("description", "")
          if tags:
            description = f"Tags: {tags}\n\n{description}"

          created = item.get("created_at")
          posted = datetime.fromtimestamp(created, tz=UTC).strftime("%Y-%m-%d") if isinstance(created, (int, float)) else parse_date(str(created))

          jobs.append(
            Job(
              source=self.name,
              board=self.name,
              company=item.get("company_name") or "Unknown",
              job_id=job_id,
              title=title,
              url=job_url,
              location=item.get("location") or "",
              remote=True if item.get("remote") else None,
              description=clean_html(description),
              posted=posted,
            )
          )

        except Exception as e:
          logger.error(f"Error parsing {self.name} job {job_id}: {e}")
          continue

      url = (data.get("links") or {}).get("next")

      if url:
        time.sleep(1.5)

    return jobs
