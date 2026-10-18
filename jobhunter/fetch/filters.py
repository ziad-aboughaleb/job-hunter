"""The rules that decide which jobs are worth showing to the AI.

Each rule is one small method that returns a short *reason* if the job should be dropped, or None
to let it through. Rules run in the order listed in JobFilter.reject_reason(); the first rule that
rejects a job wins. The reason strings appear in data/run_status.json ("dropped"), so you can see
which rule removes the most jobs and tune it.

    reason               rule
    -------------------  ----------------------------------------------------------------
    company_excluded     company is in filters.company_exclude
    title_no_match       title contains none of filters.title_include
    title_excluded       title contains a word from filters.title_exclude
    not_remote           filters.require_remote is on and the job is not remote
    location_excluded    location contains a location_exclude_terms word (and no allow word)
    location_missing     location_require_terms is set and the location matches none of them
    too_old              posted more than filters.max_age_days ago
    stack_mismatch       fewer than filters.min_stack_hits of stack_keywords appear
"""
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from jobhunter.helpers.models import Job
from jobhunter.helpers.textutil import term_in

# Personio-style sources have no remote flag; for those we may need to read the start of the description.
REMOTE_HINT_CHARS = 1500


def _norm(text: str) -> str:
    """Lowercase letters and digits only, so 'Meta-Base Inc.' and 'metabase inc' compare equal."""
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


class JobFilter:
    def __init__(self, filters_config: Dict[str, Any], now: Optional[datetime] = None):
        self.f = filters_config
        self.now = now or datetime.now(timezone.utc)
        # Compile the stack keywords once. Whole-word matching, so "go" does not match "google".
        self._stack_patterns = [re.compile(r"(?<!\w)" + re.escape(k.strip().lower()) + r"(?!\w)")
                                for k in self.f["stack_keywords"] if k.strip()]

    # ------------------------------------------------------------------ #
    def reject_reason(self, job: Job) -> Optional[str]:
        """Why this job should be dropped, or None if it passes every rule.

        Also sets job.priority and (when the job gets that far) job.stack_hits.
        """
        job.priority = self._company_in(job, "company_priority")
        for rule in (self._company_excluded, self._title_not_included, self._title_excluded,
                     self._not_remote, self._location_excluded, self._location_missing,
                     self._too_old, self._stack_mismatch):
            reason = rule(job)
            if reason:
                return reason
        return None

    # ------------------------------------------------------------------ #
    def _company_in(self, job: Job, key: str) -> bool:
        """Substring match on the company name, ignoring case and punctuation."""
        name = _norm(job.company)
        return any(_norm(term) and _norm(term) in name for term in self.f[key])

    def _company_excluded(self, job: Job) -> Optional[str]:
        return "company_excluded" if self._company_in(job, "company_exclude") else None

    def _title_not_included(self, job: Job) -> Optional[str]:
        title = job.title.lower()
        # Substring on purpose: "react" should also catch "ReactJS". The stack rule filters out the noise.
        return None if any(t.strip().lower() in title for t in self.f["title_include"] if t.strip()) else "title_no_match"

    def _title_excluded(self, job: Job) -> Optional[str]:
        # Whole words on purpose: "java" must not drop "JavaScript".
        return "title_excluded" if any(term_in(job.title, t) for t in self.f["title_exclude"]) else None

    def _not_remote(self, job: Job) -> Optional[str]:
        if not self.f["require_remote"]:
            return None
        location, title = job.location.lower(), job.title.lower()
        remote = bool(job.remote) or "remote" in location or "remote" in title
        if not remote and not location:  # no location given: read the start of the description
            remote = "remote" in job.description[:REMOTE_HINT_CHARS].lower()
        return None if remote else "not_remote"

    def _location_excluded(self, job: Job) -> Optional[str]:
        # An allow term rescues a job that also contains an exclude term: "Remote - US or Worldwide" passes.
        excluded = any(term_in(job.location, t) for t in self.f["location_exclude_terms"])
        allowed = any(term_in(job.location, t) for t in self.f["location_allow_terms"])
        return "location_excluded" if excluded and not allowed else None

    def _location_missing(self, job: Job) -> Optional[str]:
        required = self.f["location_require_terms"]
        if not required:
            return None
        return None if any(term_in(job.location, t) for t in required) else "location_missing"

    def _too_old(self, job: Job) -> Optional[str]:
        if job.posted and self.now - job.posted > timedelta(days=self.f["max_age_days"]):
            return "too_old"
        return None  # jobs with no date are kept

    def _stack_mismatch(self, job: Job) -> Optional[str]:
        text = f"{job.title}\n{job.description}".lower()
        job.stack_hits = sum(1 for pattern in self._stack_patterns if pattern.search(text))
        if job.priority:  # priority companies skip this rule (but still get a stack_hits count for ranking)
            return None
        return "stack_mismatch" if job.stack_hits < self.f["min_stack_hits"] else None
