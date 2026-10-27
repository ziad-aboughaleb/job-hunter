import httpx

from jobhunter.core.http import fetch_json
from jobhunter.core.logger import get_logger
from jobhunter.core.textutil import clean_html, parse_date
from jobhunter.models import Job
from jobhunter.sources.base import BaseSource

logger = get_logger(__name__)


class Source(BaseSource):
  name = "workable"
  domains = ["workable.com"]

  @staticmethod
  def _parse_location(item: dict, location_obj: dict) -> str:
    """Extracts and formats location data from Workable's messy location fields."""
    parts = [
      item.get("city") or location_obj.get("city"),
      item.get("state") or location_obj.get("region"),
      item.get("country") or location_obj.get("country"),
    ]
    text = ", ".join(p for p in parts if p)

    if text:
      return text

    names = []

    for entry in item.get("locations") or []:
      if isinstance(entry, dict):
        names.append(", ".join(x for x in (entry.get("city"), entry.get("region"), entry.get("country")) if x))

    return " / ".join(n for n in names if n)

  def fetch(self, slug: str = "", **kwargs) -> list[Job]:
    """Fetches job listings from a specific company's Workable widget API."""
    if not slug:
      raise ValueError(f"A company slug must be provided to fetch {self.name} jobs.")

    url = f"https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true"

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

      job_id = str(item.get("shortcode") or item.get("id") or item.get("code") or "")
      title = str(item.get("title") or "")
      job_url = str(item.get("url") or item.get("shortlink") or item.get("application_url") or "")

      if not all([job_id, title, job_url]):
        logger.warning(f"Skipping {self.name} item with missing required fields: {item}")
        continue

      try:
        loc_val = item.get("location")
        location_obj = loc_val if isinstance(loc_val, dict) else {}
        is_remote = bool(item.get("telecommuting")) or bool(location_obj.get("telecommuting"))

        jobs.append(
          Job(
            source=self.name,
            board=slug,
            company=data.get("name") or slug.replace("-", " ").title(),
            job_id=job_id,
            title=title,
            url=job_url,
            location=self._parse_location(item, location_obj),
            remote=True if is_remote else None,
            description=clean_html(item.get("description") or item.get("full_description") or ""),
            posted=parse_date(item.get("published_on") or item.get("created_at")),
          )
        )

      except Exception as e:
        logger.error(f"Error parsing {self.name} job {job_id}: {e}")
        continue

    return jobs
