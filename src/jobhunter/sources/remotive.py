from urllib.parse import quote

import httpx

from jobhunter.core.textutil import clean_html, parse_date
from jobhunter.models import Job
from jobhunter.sources.base import BaseSource


class Source(BaseSource):
  name = "remotive"
  domains = ["remotive.com", "remotive.io"]
  is_aggregator = True

  def fetch(self, category: str = "software-dev", limit: int = 300, **kwargs) -> list[Job]:
    """Fetches remote job listings from the Remotive API."""
    url = f"https://remotive.com/api/remote-jobs?limit={limit}"

    if category:
      url += f"&category={quote(category)}"

    try:
      response = httpx.get(url, timeout=15.0)
      response.raise_for_status()
      data = response.json()
    except httpx.HTTPError as e:
      print(f"Failed to fetch from Remotive: {e}")
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
