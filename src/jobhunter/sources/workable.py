from jobhunter.core.http import fetch_json
from jobhunter.core.textutil import clean_html, parse_date
from jobhunter.models import Job
from jobhunter.sources.base import BaseSource


class Source(BaseSource):
  name = "workable"
  domains = ["workable.com"]
  is_aggregator = False

  @staticmethod
  def _parse_location(item: dict, location_obj: dict) -> str:
    """Extracts and formats location data from Workable's messy location fields."""
    parts = [
      item.get("city") or location_obj.get("city"),
      item.get("state") or location_obj.get("region"),
      item.get("country") or location_obj.get("country"),
    ]
    text = ", ".join(p for p in parts if p)

    if text:
      return text

    names = []

    for entry in item.get("locations") or []:
      if isinstance(entry, dict):
        names.append(", ".join(x for x in (entry.get("city"), entry.get("region"), entry.get("country")) if x))

    return " / ".join(n for n in names if n)

  def fetch(self, slug: str = "", **kwargs) -> list[Job]:
    """Fetches job listings from a specific company's Workable widget API."""
    if not slug:
      return []

    url = f"https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true"

    data = fetch_json(url, expected_type=dict)
    if not data:
      return []

    jobs = []

    for item in data.get("jobs", []):
      location_obj = item.get("location") if isinstance(item.get("location"), dict) else {}
      is_remote = bool(item.get("telecommuting")) or bool(location_obj.get("telecommuting"))

      jobs.append(
        Job(
          source=self.name,
          board=slug,
          company=data.get("name") or slug.replace("-", " ").title(),
          job_id=str(item.get("shortcode") or item.get("id") or item.get("code") or ""),
          title=item.get("title") or "",
          url=item.get("url") or item.get("shortlink") or item.get("application_url") or "",
          location=self._parse_location(item, location_obj),
          remote=True if is_remote else None,
          description=clean_html(item.get("description") or item.get("full_description") or ""),
          posted=parse_date(item.get("published_on") or item.get("created_at")),
        )
      )

    return jobs
