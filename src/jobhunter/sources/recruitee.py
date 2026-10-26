import httpx

from jobhunter.core.textutil import clean_html, parse_date
from jobhunter.models import Job
from jobhunter.sources.base import BaseSource


class Source(BaseSource):
  name = "recruitee"
  domains = ["recruitee.com"]
  is_aggregator = False

  def fetch(self, slug: str = "", **kwargs) -> list[Job]:
    """Fetches job listings from a specific company's Recruitee API."""
    if not slug:
      return []

    url = f"https://{slug}.recruitee.com/api/offers/"

    try:
      response = httpx.get(url, timeout=15.0)
      response.raise_for_status()
      data = response.json()
    except httpx.HTTPError as e:
      print(f"Failed to fetch {slug} from Recruitee: {e}")
      return []

    if not isinstance(data, dict):
      return []

    jobs = []

    for item in data.get("offers", []):
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
          job_id=str(item.get("id") or item.get("guid") or item.get("slug") or ""),
          title=item.get("title") or "",
          url=item.get("careers_url") or item.get("url") or "",
          location=location or "",
          remote=True if item.get("remote") else None,
          posted=parse_date(item.get("published_at") or item.get("created_at")),
          description=description,
        )
      )

    return jobs
