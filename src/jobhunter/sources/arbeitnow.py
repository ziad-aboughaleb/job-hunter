import datetime

import httpx

from jobhunter.core.textutil import clean_html, parse_date
from jobhunter.models import Job
from jobhunter.sources.base import BaseSource


class Source(BaseSource):
  name = "arbeitnow"
  domains = ["arbeitnow.com"]
  is_aggregator = True

  def fetch(self, pages: int = 2, **kwargs) -> list[Job]:
    """Fetches job listings from the Arbeitnow API (supports pagination)."""
    url = "https://www.arbeitnow.com/api/job-board-api"

    jobs = []

    for _ in range(pages):
      if not url:
        break

      try:
        response = httpx.get(url, timeout=15.0)
        response.raise_for_status()
        data = response.json()
      except httpx.HTTPError as e:
        print(f"Failed to fetch from Arbeitnow: {e}")
        break

      for item in data.get("data", []):
        tags = ", ".join(item.get("tags") or [])
        description = item.get("description", "")
        if tags:
          description = f"Tags: {tags}\n\n{description}"

        # Arbeitnow returns epoch seconds; convert it to YYYY-MM-DD
        created = item.get("created_at")

        if isinstance(created, (int, float)):
          posted = datetime.datetime.fromtimestamp(created, tz=datetime.UTC).strftime("%Y-%m-%d")
        else:
          posted = parse_date(str(created))

        jobs.append(
          Job(
            source=self.name,
            board=self.name,
            company=item.get("company_name") or "Unknown",
            job_id=str(item.get("slug", "")),
            title=item.get("title") or "",
            url=item.get("url") or "",
            location=item.get("location") or "",
            remote=True if item.get("remote") else None,
            description=clean_html(description),
            posted=posted,
          )
        )

      url = (data.get("links") or {}).get("next")

    return jobs
