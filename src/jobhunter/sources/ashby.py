import httpx

from jobhunter.core.http import fetch_json
from jobhunter.core.logger import get_logger
from jobhunter.core.textutil import clean_html, parse_date
from jobhunter.models import Job
from jobhunter.sources.base import BaseSource

logger = get_logger(__name__)


class Source(BaseSource):
  name = "ashby"
  domains = ["ashbyhq.com"]

  def fetch(self, slug: str = "", **kwargs) -> list[Job]:
    """Fetches job listings from a specific company's Ashby API."""
    if not slug:
      raise ValueError(f"A company slug must be provided to fetch {self.name} jobs.")

    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"

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

      if item.get("isListed") is False:
        continue

      job_id = str(item.get("id") or "")
      title = str(item.get("title") or "")
      job_url = str(item.get("jobUrl") or item.get("applyUrl") or "")

      if not all([job_id, title, job_url]):
        logger.warning(f"Skipping {self.name} item with missing required fields: {item}")
        continue

      try:
        extra = [s.get("location", "") if isinstance(s, dict) else str(s) for s in item.get("secondaryLocations") or []]
        location = ", ".join(x for x in [item.get("location", ""), *extra] if x)

        is_remote = bool(item.get("isRemote")) or str(item.get("workplaceType", "")).lower() == "remote"

        jobs.append(
          Job(
            source=self.name,
            board=slug,
            company=slug.replace("-", " ").title(),
            job_id=job_id,
            title=title,
            url=job_url,
            location=location,
            remote=True if is_remote else None,
            posted=parse_date(item.get("publishedAt") or item.get("publishedDate")),
            description=item.get("descriptionPlain") or clean_html(item.get("descriptionHtml", "")),
          )
        )

      except Exception as e:
        logger.error(f"Error parsing {self.name} job {job_id} for {slug}: {e}")
        continue

    return jobs
