import logging
import re

from jobhunter.core.http import fetch_url
from jobhunter.core.logger import console
from jobhunter.core.textutil import clean_html, parse_date
from jobhunter.models import Job
from jobhunter.sources.base import BaseSource

logger = logging.getLogger(__name__)


class Source(BaseSource):
  name = "ashby"
  domains = ["jobs.ashbyhq.com"]
  url_patterns = [re.compile(r"(?://|www\.)(?P<slug>[^/?#.]+)\.ashbyhq\.com"), re.compile(r"ashbyhq\.com/(?P<slug>[^/?#]+)")]

  def fetch(self, slug: str = "", skip_parsing: bool = False, **kwargs) -> list[Job]:
    """Fetches job listings from a specific company's Ashby API."""
    if not slug:
      raise ValueError(f"A company slug must be provided to fetch {self.name} jobs.")

    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    data = fetch_url(url, expected_type=dict)

    if skip_parsing:
      return []

    jobs: list[Job] = []

    for item in data.get("jobs", []):
      if not isinstance(item, dict):
        logger.warning(f"[ {self.name} ] Skipping unexpected item format: {type(item).__name__}")
        console.print(f"  [yellow]⚠ [ {self.name} ] Skipping unexpected item format...[/yellow]")
        continue

      if item.get("isListed") is False:
        continue

      job_id = str(item.get("id") or "")
      title = str(item.get("title") or "")
      job_url = str(item.get("jobUrl") or item.get("applyUrl") or "")

      if not all([job_id, title, job_url]):
        logger.warning(f"[ {self.name} ] Skipping item with missing required fields: {item}")
        console.print(f"  [yellow]⚠ [ {self.name} ] Skipping item with missing required fields.[/yellow]")
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
        logger.exception(f"[ {self.name} ] Error parsing job '{job_id}' for '{slug}': {e}")
        console.print(f"  [red]✖ [ {self.name} ] Error parsing job '{job_id}'[/red]")
        continue

    return jobs
