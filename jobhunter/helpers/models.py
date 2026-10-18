"""The one data structure every source produces and every later stage consumes."""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Job:
    """A job posting, in the same shape no matter which website it came from."""

    source: str  # which kind of site: "greenhouse", "remotive", ...
    board: str  # which board on that site: the company slug, or the site name for aggregators
    company: str
    title: str
    url: str
    job_id: str = ""
    location: str = ""
    description: str = ""  # plain text, not HTML
    remote: Optional[bool] = None  # True if the site says remote; None if it does not say
    posted: Optional[datetime] = None

    # Filled in by the filters:
    stack_hits: int = 0  # how many of your stack_keywords appear in the posting
    priority: bool = False  # company is in your company_priority list

    @property
    def uid(self) -> str:
        """Stable identity, used to remember which jobs have been dealt with."""
        return f"{self.source}:{self.board}:{self.job_id or self.url}"
