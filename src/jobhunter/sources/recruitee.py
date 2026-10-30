import logging
import re

from jobhunter.core.http import fetch_url
from jobhunter.core.logger import console
from jobhunter.core.textutil import clean_html, parse_date
from jobhunter.models import Job
from jobhunter.sources.base import BaseSource

logger = logging.getLogger(__name__)


class Source(BaseSource):
  name = "recruitee"
  domains = ["recruitee.com"]
  url_patterns = [re.compile(r"(?://|www\.)?(?P<slug>[a-zA-Z0-9-]+)\.recruitee\.com")]

  def fetch(self, slug: str = "", skip_parsing: bool = False, **kwargs) -> list[Job]:
    """Fetches job listings from a specific company's Recruitee API."""
    if not slug:
      raise ValueError(f"A company slug must be provided to fetch {self.name} jobs.")

    url = f"https://{slug}.recruitee.com/api/offers/"
    data = fetch_url(url, expected_type=dict)

    if skip_parsing:
      return []

    jobs: list[Job] = []

    for item in data.get("offers", []):
      if not isinstance(item, dict):
        logger.warning(f"[ {self.name} ] Skipping unexpected item format: {type(item).__name__}")
        console.print(f"  [yellow]⚠ [ {self.name} ] Skipping unexpected item format...[/yellow]")
        continue

      job_id = str(item.get("id") or item.get("guid") or item.get("slug") or "")
      title = str(item.get("title") or "")
      job_url = str(item.get("careers_url") or item.get("url") or "")

      if not all([job_id, title, job_url]):
        logger.warning(f"[ {self.name} ] Skipping item with missing required fields: {item}")
        console.print(f"  [yellow]⚠ [ {self.name} ] Skipping item with missing required fields.[/yellow]")
        continue

      try:
        location = item.get("location") or ", ".join(x for x in (item.get("city"), item.get("country")) if x)

        description = "\n\n".join(
          x
          for x in (
            clean_html(item.get("description")),
            clean_html(item.get("requirements")),
          )
          if x
        )

        jobs.append(
          Job(
            source=self.name,
            board=slug,
            company=item.get("company_name") or slug.replace("-", " ").title(),
            job_id=job_id,
            title=title,
            url=job_url,
            location=location or "",
            remote=True if item.get("remote") else None,
            posted=parse_date(item.get("published_at") or item.get("created_at")),
            description=description,
          )
        )

      except Exception as e:
        logger.exception(f"[ {self.name} ] Error parsing job '{job_id}' for '{slug}': {e}")
        console.print(f"  [red]✖ [ {self.name} ] Error parsing job '{job_id}'[/red]")
        continue

    return jobs
