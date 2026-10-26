import httpx

from jobhunter.core.textutil import clean_html, parse_date
from jobhunter.models import Job
from jobhunter.sources.base import BaseSource


class Source(BaseSource):
  name = "ashby"
  domains = ["ashbyhq.com"]
  is_aggregator = False

  def fetch(self, slug: str = "", **kwargs) -> list[Job]:
    """Fetches job listings from a specific company's Ashby API."""
    if not slug:
      return []

    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"

    try:
      response = httpx.get(url, timeout=15.0)
      response.raise_for_status()
      data = response.json()
    except httpx.HTTPError as e:
      print(f"Failed to fetch {slug} from Ashby: {e}")
      return []

    if not isinstance(data, dict):
      return []

    company = slug.replace("-", " ").title()
    jobs = []

    for item in data.get("jobs", []):
      if item.get("isListed") is False:
        continue

      extra = [s.get("location", "") if isinstance(s, dict) else str(s) for s in item.get("secondaryLocations") or []]
      location = ", ".join(x for x in [item.get("location", ""), *extra] if x)

      is_remote = bool(item.get("isRemote")) or str(item.get("workplaceType", "")).lower() == "remote"

      jobs.append(
        Job(
          source=self.name,
          board=slug,
          company=company,
          job_id=str(item.get("id", "")),
          title=item.get("title") or "",
          url=item.get("jobUrl") or item.get("applyUrl") or "",
          location=location,
          remote=True if is_remote else None,
          posted=parse_date(item.get("publishedAt") or item.get("publishedDate")),
          description=item.get("descriptionPlain") or clean_html(item.get("descriptionHtml", "")),
        )
      )

    return jobs
