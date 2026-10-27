import logging

import httpx

from jobhunter.core.http import fetch_json
from jobhunter.core.textutil import clean_html, parse_date
from jobhunter.models import Job
from jobhunter.sources.base import BaseSource

logger = logging.getLogger(__name__)


class Source(BaseSource):
  name = "greenhouse"
  domains = ["greenhouse.io"]

  def fetch(self, slug: str = "", **kwargs) -> list[Job]:
    """Fetches job listings from a specific company's Greenhouse board."""
    if not slug:
      raise ValueError(f"A company slug must be provided to fetch {self.name} jobs.")

    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"

    try:
      data = fetch_json(url, expected_type=dict)
    except httpx.HTTPStatusError:
      raise
    except (httpx.HTTPError, ValueError) as e:
      raise RuntimeError(f"Failed to fetch {self.name} jobs for {slug}: {e}") from e

    if not isinstance(data, dict):
      return []

    jobs = []

    for item in data.get("jobs", []):
      if not isinstance(item, dict):
        logger.warning(f"Skipping unexpected item format from {self.name}: {type(item)}")
        continue

      job_id = str(item.get("id") or "")
      title = str(item.get("title") or "")
      job_url = str(item.get("absolute_url") or "")

      if not all([job_id, title, job_url]):
        logger.warning(f"Skipping {self.name} item with missing required fields: {item}")
        continue

      try:
        location = (item.get("location") or {}).get("name") or ""

        jobs.append(
          Job(
            source=self.name,
            board=slug,
            company=slug.replace("-", " ").title(),
            job_id=job_id,
            title=title,
            url=job_url,
            location=location,
            posted=parse_date(item.get("first_published") or item.get("updated_at")),
            description=clean_html(item.get("content", "")),
          )
        )

      except Exception as e:
        logger.error(f"Error parsing {self.name} job {job_id}: {e}")
        continue

    return jobs
