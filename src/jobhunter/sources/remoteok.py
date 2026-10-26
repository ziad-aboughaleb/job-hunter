from jobhunter.core.http import fetch_json
from jobhunter.core.settings import settings
from jobhunter.core.textutil import clean_html, parse_date
from jobhunter.models import Job
from jobhunter.sources.base import BaseSource


class Source(BaseSource):
  name = "remoteok"
  domains = ["remoteok.com"]
  is_aggregator = True
  board_config = settings.boards.get("remotive", {})
  enabled = board_config.get("enabled", True) if isinstance(board_config, dict) else bool(board_config)

  def fetch(self, slug: str = "", **kwargs) -> list[Job]:
    """Fetches remote job listings from RemoteOK API."""
    if not self.enabled:
      return []

    url = "https://remoteok.com/api"

    data = fetch_json(url, expected_type=list)
    if not data:
      return []

    jobs = []

    for item in data:
      # Skip non-dict items and RemoteOK's legal/meta notice header block
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
