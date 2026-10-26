from datetime import UTC, datetime

import httpx

from jobhunter.core.textutil import clean_html, parse_date
from jobhunter.models import Job
from jobhunter.sources.base import BaseSource


class Source(BaseSource):
  name = "lever"
  domains = ["lever.co"]
  is_aggregator = False

  def fetch(self, slug: str = "", is_eu: bool = False, **kwargs) -> list[Job]:
    """Fetches job listings from a specific company's Lever API."""
    if not slug:
      return []

    is_eu = is_eu or kwargs.get("eu", False)
    host = "api.eu.lever.co" if is_eu else "api.lever.co"
    url = f"https://{host}/v0/postings/{slug}?mode=json"

    try:
      response = httpx.get(url, timeout=15.0)
      response.raise_for_status()
      data = response.json()
    except httpx.HTTPError as e:
      print(f"Failed to fetch {slug} from Lever ({host}): {e}")
      return []

    if not isinstance(data, list):
      return []

    company = slug.replace("-", " ").title()
    jobs = []

    for item in data:
      categories = item.get("categories") or {}
      location = categories.get("location") or ", ".join(categories.get("allLocations") or [])

      parts = [item.get("descriptionPlain") or ""]
      for block in item.get("lists") or []:
        block_text = block.get("text") or ""
        block_content = clean_html(block.get("content") or "")
        parts.append(f"{block_text}\n{block_content}")
      parts.append(item.get("additionalPlain") or "")

      is_remote = str(item.get("workplaceType", "")).lower() == "remote"

      created_raw = item.get("createdAt")
      posted = datetime.fromtimestamp(created_raw / 1000, tz=UTC).isoformat() if isinstance(created_raw, int) else parse_date(created_raw)

      jobs.append(
        Job(
          source="lever_eu" if is_eu else self.name,
          board=slug,
          company=company,
          job_id=str(item.get("id", "")),
          title=item.get("text") or "",
          url=item.get("hostedUrl") or "",
          location=location or "",
          remote=True if is_remote else None,
          posted=posted,
          description="\n\n".join(p for p in parts if p).strip(),
        )
      )

    return jobs
