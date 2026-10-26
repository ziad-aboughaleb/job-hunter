from jobhunter.core.http import fetch_json
from jobhunter.core.textutil import clean_html, parse_date
from jobhunter.models import Job
from jobhunter.sources.base import BaseSource


class Source(BaseSource):
  name = "greenhouse"
  domains = ["greenhouse.io"]

  def fetch(self, slug: str = "", **kwargs) -> list[Job]:
    """Fetches job listings from a specific company's Greenhouse board."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"

    data = fetch_json(url, expected_type=dict)
    if not data:
      return []

    jobs = []

    for item in data.get("jobs", []):
      jobs.append(
        Job(
          source=self.name,
          board=slug,
          company=slug.replace("-", " ").title(),
          job_id=str(item.get("id", "")),
          title=item.get("title") or "",
          url=item.get("absolute_url") or "",
          location=(item.get("location") or {}).get("name") or "",
          posted=parse_date(item.get("first_published") or item.get("updated_at")),
          description=clean_html(item.get("content", "")),
        )
      )

    return jobs
