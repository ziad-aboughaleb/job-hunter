import logging

from jobhunter.core.http import fetch_url
from jobhunter.core.textutil import clean_html, parse_date
from jobhunter.models import Job
from jobhunter.sources.base import BaseSource

logger = logging.getLogger(__name__)


class Source(BaseSource):
  name = "remoteok"
  domains = ["remoteok.com"]
  is_aggregator = True

  def fetch(self, slug: str = "", **kwargs) -> list[Job]:
    """Fetches job listings from a specific company's RemoteOK API."""
    url = "https://remoteok.com/api"
    data = fetch_url(url, expected_type=list)
    jobs: list[Job] = []

    for item in data:
      if not isinstance(item, dict):
        logger.warning(f"[{self.name}] Skipping unexpected item format: {type(item).__name__}")
        continue

      if "legal" in item:
        continue

      job_id = str(item.get("id") or item.get("slug") or "")
      title = str(item.get("position") or "")
      job_url = str(item.get("url") or item.get("apply_url") or "")

      if not all([job_id, title, job_url]):
        logger.warning(f"[{self.name}] Skipping item with missing required fields: {item}")
        continue

      try:
        raw_tags = item.get("tags") or []
        tags = ", ".join(str(t) for t in raw_tags if t)
        description = item.get("description", "")

        if tags:
          description = f"Tags: {tags}\n\n{description}"

        jobs.append(
          Job(
            source=self.name,
            board=self.name,
            company=item.get("company") or "Unknown",
            job_id=job_id,
            title=title,
            url=job_url,
            location=item.get("location") or "Remote",
            remote=True,
            posted=parse_date(item.get("date")),
            description=clean_html(description),
          )
        )

      except Exception as e:
        logger.error(f"[{self.name}] Error parsing job '{job_id}': {e}")
        continue

    return jobs
