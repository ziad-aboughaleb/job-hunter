from jobhunter.core.http import fetch_json
from jobhunter.core.textutil import clean_html, parse_date
from jobhunter.models import Job
from jobhunter.sources.base import BaseSource


class Source(BaseSource):
  name = "ashby"
  domains = ["ashbyhq.com"]

  def fetch(self, slug: str = "", **kwargs) -> list[Job]:
    """Fetches job listings from a specific company's Ashby API."""
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"

    data = fetch_json(url, expected_type=dict)
    if not data:
      return []

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
          company=slug.replace("-", " ").title(),
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
