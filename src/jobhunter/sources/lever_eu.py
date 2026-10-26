from datetime import UTC, datetime

from jobhunter.core.http import fetch_json
from jobhunter.core.textutil import clean_html, parse_date
from jobhunter.models import Job
from jobhunter.sources.base import BaseSource


class Source(BaseSource):
  name = "lever_eu"
  domains = ["eu.lever.co"]

  def fetch(self, slug: str = "", **kwargs) -> list[Job]:
    """Fetches job listings from a specific company's Lever EU API."""
    url = f"https://api.eu.lever.co/v0/postings/{slug}?mode=json"

    data = fetch_json(url, expected_type=list)
    if not data:
      return []

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
          source=self.name,
          board=slug,
          company=slug.replace("-", " ").title(),
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
