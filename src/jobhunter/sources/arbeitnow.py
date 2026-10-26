import time
from datetime import UTC, datetime

from jobhunter.core.http import fetch_json
from jobhunter.core.settings import settings
from jobhunter.core.textutil import clean_html, parse_date
from jobhunter.models import Job
from jobhunter.sources.base import BaseSource


class Source(BaseSource):
  name = "arbeitnow"
  domains = ["arbeitnow.com"]
  is_aggregator = True
  board_config = settings.boards.get("arbeitnow", {})
  enabled = board_config.get("enabled", True) if isinstance(board_config, dict) else bool(board_config)

  def fetch(self, slug: str = "", **kwargs) -> list[Job]:
    """Fetches all available job listings from the Arbeitnow API via pagination link traversal."""
    if not self.enabled:
      return []

    url = "https://www.arbeitnow.com/api/job-board-api"

    jobs = []

    while url:
      data = fetch_json(url, expected_type=dict)
      if not data:
        break

      for item in data.get("data", []):
        tags = ", ".join(item.get("tags") or [])
        description = item.get("description", "")
        if tags:
          description = f"Tags: {tags}\n\n{description}"

        created = item.get("created_at")
        posted = datetime.fromtimestamp(created, tz=UTC).strftime("%Y-%m-%d") if isinstance(created, (int, float)) else parse_date(str(created))

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

      # Paginate until the API returns a null/empty next link
      url = (data.get("links") or {}).get("next")

      if url:
        time.sleep(1.5)

    return jobs
