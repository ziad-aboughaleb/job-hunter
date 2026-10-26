from jobhunter.core.http import fetch_json
from jobhunter.core.textutil import clean_html, parse_date
from jobhunter.models import Job
from jobhunter.sources.base import BaseSource


class Source(BaseSource):
  name = "recruitee"
  domains = ["recruitee.com"]
  is_subdomain = True

  def fetch(self, slug: str = "", **kwargs) -> list[Job]:
    """Fetches job listings from a specific company's Recruitee API."""
    url = f"https://{slug}.recruitee.com/api/offers/"

    data = fetch_json(url, expected_type=dict)
    if not data:
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
