import httpx

from jobhunter.core.http import fetch_json
from jobhunter.core.logger import get_logger
from jobhunter.core.textutil import clean_html, parse_date
from jobhunter.models import Job
from jobhunter.sources.base import BaseSource

logger = get_logger(__name__)


class Source(BaseSource):
  name = "remoteok"
  domains = ["remoteok.com"]
  is_aggregator = True

  def fetch(self, slug: str = "", **kwargs) -> list[Job]:
    """Fetches remote job listings from RemoteOK API."""
    url = "https://remoteok.com/api"

    try:
      data = fetch_json(url, expected_type=list)
    except httpx.HTTPStatusError:
      raise
    except (httpx.HTTPError, ValueError) as e:
      raise RuntimeError(f"Failed to fetch {self.name} jobs from {url}: {e}") from e

    if not isinstance(data, list):
      return []

    jobs = []

    for item in data:
      if not isinstance(item, dict):
        logger.warning(f"Skipping unexpected item format from {self.name}: {type(item)}")
        continue

      if "legal" in item:
        continue

      job_id = str(item.get("id") or item.get("slug") or "")
      title = str(item.get("position") or "")
      job_url = str(item.get("url") or item.get("apply_url") or "")

      if not all([job_id, title, job_url]):
        logger.warning(f"Skipping {self.name} item with missing required fields: {item}")
        continue

      try:
        tags = ", ".join(item.get("tags") or [])
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
            description=clean_html(description),
            posted=parse_date(item.get("date")),
          )
        )

      except Exception as e:
        logger.error(f"Error parsing {self.name} job {job_id}: {e}")
        continue

    return jobs
