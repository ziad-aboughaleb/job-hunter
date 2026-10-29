import logging
import time
from datetime import UTC, datetime

from jobhunter.core.http import fetch_url
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
    jobs: list[Job] = []

    while url:
      data = fetch_url(url, expected_type=dict)

      for item in data.get("data", []):
        if not isinstance(item, dict):
          logger.warning(f"[{self.name}] Skipping unexpected item format: {type(item).__name__}")
          continue

        job_id = str(item.get("slug") or "")
        title = str(item.get("title") or "")
        job_url = str(item.get("url") or "")

        if not all([job_id, title, job_url]):
          logger.warning(f"[{self.name}] Skipping item with missing required fields: {item}")
          continue

        try:
          raw_tags = item.get("tags") or []
          tags = ", ".join(str(t) for t in raw_tags if t)
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
              posted=posted,
              description=clean_html(description),
            )
          )

        except Exception as e:
          logger.error(f"[{self.name}] Error parsing job '{job_id}': {e}")
          continue

      url = (data.get("links") or {}).get("next")

      if url:
        time.sleep(1.5)

    return jobs
