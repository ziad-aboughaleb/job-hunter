import logging
import re

from jobhunter.core.http import fetch_url
from jobhunter.core.logger import console
from jobhunter.core.textutil import clean_html, parse_date
from jobhunter.models import Job
from jobhunter.sources.base import BaseSource

logger = logging.getLogger(__name__)


class Source(BaseSource):
  name = "workable"
  domains = ["apply.workable.com"]
  url_patterns = [
    re.compile(r"apply\.workable\.com/(?P<slug>[^/?#]+)"),
  ]

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

  def fetch(self, slug: str = "", skip_parsing: bool = False, **kwargs) -> list[Job]:
    """Fetches job listings from a specific company's Workable API."""
    if not slug:
      raise ValueError(f"A company slug must be provided to fetch {self.name} jobs.")

    url = f"https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true"
    data = fetch_url(url, expected_type=dict)

    if skip_parsing:
      return []

    jobs: list[Job] = []

    for item in data.get("jobs", []):
      if not isinstance(item, dict):
        logger.warning(f"[ {self.name} ] Skipping unexpected item format: {type(item).__name__}")
        console.print(f"  [yellow]⚠ [ {self.name} ] Skipping unexpected item format...[/yellow]")
        continue

      job_id = str(item.get("shortcode") or item.get("id") or item.get("code") or "")
      title = str(item.get("title") or "")
      job_url = str(item.get("url") or item.get("shortlink") or item.get("application_url") or "")

      if not all([job_id, title, job_url]):
        logger.warning(f"[ {self.name} ] Skipping item with missing required fields: {item}")
        console.print(f"  [yellow]⚠ [ {self.name} ] Skipping item with missing required fields.[/yellow]")
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
            posted=parse_date(item.get("published_on") or item.get("created_at")),
            description=clean_html(item.get("description") or item.get("full_description") or ""),
          )
        )

      except Exception as e:
        logger.exception(f"[ {self.name} ] Error parsing job '{job_id}' for '{slug}': {e}")
        console.print(f"  [red]✖ [ {self.name} ] Error parsing job '{job_id}'[/red]")
        continue

    return jobs
