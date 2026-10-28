import httpx

from jobhunter.core.http import fetch_json
from jobhunter.core.logger import get_logger
from jobhunter.core.textutil import clean_html, parse_date
from jobhunter.models import Job
from jobhunter.sources.base import BaseSource

logger = get_logger(__name__)


class Source(BaseSource):
  name = "remotive"
  domains = ["remotive.com", "remotive.io"]
  is_aggregator = True

  def fetch(self, slug: str = "", **kwargs) -> list[Job]:
    """Fetches remote job listings from the Remotive API."""
    category = self.board_config.get("category", "software-dev") if isinstance(self.board_config, dict) else "software-dev"

    url = f"https://remotive.com/api/remote-jobs?category={category}"

    try:
      data = fetch_json(url, expected_type=dict)
    except httpx.HTTPStatusError:
      raise
    except (httpx.HTTPError, ValueError) as e:
      raise RuntimeError(f"Failed to fetch {self.name} jobs from {url}: {e}") from e

    if not isinstance(data, dict):
      return []

    jobs = []

    for item in data.get("jobs", []):
      if not isinstance(item, dict):
        logger.warning(f"Skipping unexpected item format from {self.name}: {type(item)}")
        continue

      job_id = str(item.get("id") or "")
      title = str(item.get("title") or "")
      job_url = str(item.get("url") or "")

      if not all([job_id, title, job_url]):
        logger.warning(f"Skipping {self.name} item with missing required fields: {item}")
        continue

      try:
        jobs.append(
          Job(
            source=self.name,
            board=self.name,
            company=item.get("company_name") or "Unknown",
            job_id=job_id,
            title=title,
            url=job_url,
            location=item.get("candidate_required_location") or "Remote",
            remote=True,
            posted=parse_date(item.get("publication_date")),
            description=clean_html(item.get("description", "")),
          )
        )

      except Exception as e:
        logger.error(f"Error parsing {self.name} job {job_id}: {e}")
        continue

    return jobs
