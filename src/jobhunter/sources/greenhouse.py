import httpx

from jobhunter.core.textutil import clean_html, parse_date
from jobhunter.models import Job
from jobhunter.sources.base import BaseSource


class Source(BaseSource):
  name = "greenhouse"
  domains = ["greenhouse.io"]
  is_aggregator = False

  def fetch(self, slug: str = "", **kwargs) -> list[Job]:
    """Fetches job listings from a specific company's Greenhouse board."""
    if not slug:
      return []

    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"

    try:
      response = httpx.get(url, timeout=15.0)
      response.raise_for_status()
      data = response.json()
    except httpx.HTTPError as e:
      print(f"Failed to fetch {slug} from Greenhouse: {e}")
      return []

    if not isinstance(data, dict):
      return []

    company = slug.replace("-", " ").title()
    jobs = []

    for item in data.get("jobs", []):
      jobs.append(
        Job(
          source=self.name,
          board=slug,
          company=company,
          job_id=str(item.get("id", "")),
          title=item.get("title") or "",
          url=item.get("absolute_url") or "",
          location=(item.get("location") or {}).get("name") or "",
          posted=parse_date(item.get("first_published") or item.get("updated_at")),
          description=clean_html(item.get("content", "")),
        )
      )

    return jobs
