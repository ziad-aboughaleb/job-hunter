from jobhunter.core.http import fetch_json
from jobhunter.core.textutil import clean_html, parse_date
from jobhunter.models import Job
from jobhunter.sources.base import BaseSource


class Source(BaseSource):
  name = "remotive"
  domains = ["remotive.com", "remotive.io"]
  is_aggregator = True

  def fetch(self, slug: str = "", **kwargs) -> list[Job]:
    """Fetches remote job listings from the Remotive API."""
    category = self.board_config.get("category", "software-dev") if isinstance(self.board_config, dict) else "software-dev"

    url = f"https://remotive.com/api/remote-jobs?category={category}"

    data = fetch_json(url, expected_type=dict)
    if not data:
      return []

    jobs = []

    for item in data.get("jobs", []):
      jobs.append(
        Job(
          source=self.name,
          board=self.name,
          company=item.get("company_name") or "Unknown",
          job_id=str(item.get("id", "")),
          title=item.get("title") or "",
          url=item.get("url") or "",
          location=item.get("candidate_required_location") or "Remote",
          remote=True,
          description=clean_html(item.get("description", "")),
          posted=parse_date(item.get("publication_date")),
        )
      )

    return jobs
