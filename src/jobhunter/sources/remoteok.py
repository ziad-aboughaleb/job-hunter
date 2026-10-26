import httpx

from jobhunter.core.textutil import clean_html, parse_date
from jobhunter.models import Job
from jobhunter.sources.base import BaseSource


class Source(BaseSource):
  name = "remoteok"
  domains = ["remoteok.com"]
  is_aggregator = True

  def fetch(self, **kwargs) -> list[Job]:
    """Fetches remote job listings from RemoteOK API."""
    url = "https://remoteok.com/api"

    # RemoteOK frequently blocks default Python user-agents with a 403 Forbidden.
    # Adding a standard browser User-Agent ensures the request succeeds.
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    try:
      response = httpx.get(url, headers=headers, timeout=15.0)
      response.raise_for_status()
      data = response.json()
    except httpx.HTTPError as e:
      print(f"Failed to fetch from RemoteOK: {e}")
      return []

    if not isinstance(data, list):
      return []

    jobs = []

    for item in data:
      if not isinstance(item, dict) or not item.get("position"):
        continue

      tags = ", ".join(item.get("tags") or [])
      description = item.get("description", "")

      if tags:
        description = f"Tags: {tags}\n\n{description}"

      jobs.append(
        Job(
          source=self.name,
          board=self.name,
          company=item.get("company") or "Unknown",
          job_id=str(item.get("id") or item.get("slug") or ""),
          title=item.get("position") or "",
          url=item.get("url") or item.get("apply_url") or "",
          location=item.get("location") or "Remote",
          remote=True,
          description=clean_html(description),
          posted=parse_date(item.get("date")),
        )
      )

    return jobs
