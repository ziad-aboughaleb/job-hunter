import logging

from jobhunter.core.http import fetch_url
from jobhunter.core.logger import console
from jobhunter.core.textutil import clean_html, parse_date
from jobhunter.models import Job
from jobhunter.sources.base import BaseSource

logger = logging.getLogger(__name__)


class Source(BaseSource):
  name = "remotive"
  domains = ["remotive.com", "remotive.io"]
  is_aggregator = True

  def fetch(self, slug: str = "", **kwargs) -> list[Job]:
    """Fetches job listings from Remotive API."""
    category = self.board_config.get("category", "software-dev") if isinstance(self.board_config, dict) else "software-dev"

    url = f"https://remotive.com/api/remote-jobs?category={category}"
    data = fetch_url(url, expected_type=dict)
    jobs: list[Job] = []

    for item in data.get("jobs", []):
      if not isinstance(item, dict):
        logger.warning(f"[ {self.name} ] Skipping unexpected item format: {type(item).__name__}")
        console.print(f"  [yellow]⚠ [ {self.name} ] Skipping unexpected item format...[/yellow]")
        continue

      job_id = str(item.get("id") or "")
      title = str(item.get("title") or "")
      job_url = str(item.get("url") or "")

      if not all([job_id, title, job_url]):
        logger.warning(f"[ {self.name} ] Skipping item with missing required fields: {item}")
        console.print(f"  [yellow]⚠ [ {self.name} ] Skipping item with missing required fields.[/yellow]")
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
        logger.exception(f"[ {self.name} ] Error parsing job '{job_id}': {e}")
        console.print(f"  [red]✖ [ {self.name} ] Error parsing job '{job_id}'[/red]")
        continue

    return jobs
