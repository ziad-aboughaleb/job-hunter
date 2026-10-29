import datetime
import re
from functools import lru_cache

from jobhunter.core.settings import settings
from jobhunter.models import Job


@lru_cache(maxsize=512)
def _get_word_pattern(keyword: str) -> re.Pattern:
  """Compiles and caches word boundary regex patterns for tech keywords."""
  return re.compile(rf"(?<![a-z0-9]){re.escape(keyword.lower())}(?![a-z0-9])")


def has_word(keyword: str, text: str) -> bool:
  """Checks if a keyword exists in the text as a whole word, ignoring case."""
  if not text or not keyword:
    return False
  return bool(_get_word_pattern(keyword).search(text.lower()))


def is_valid_title(job: Job) -> bool:
  """Checks if the job title passes the include/exclude filters."""
  title = (job.title or "").lower()
  filters = settings.filters

  is_excluded = bool(filters.title_exclude and any(has_word(ex, title) for ex in filters.title_exclude))

  is_included = not filters.title_include or any(has_word(inc, title) for inc in filters.title_include)

  return is_included and not is_excluded


def is_valid_company(job: Job) -> bool:
  """Checks if the job company passes the exclude filters."""
  company = (job.company or "").lower()
  filters = settings.filters

  is_excluded = bool(filters.company_exclude and any(has_word(ex, company) for ex in filters.company_exclude))

  return not is_excluded


def is_valid_location(job: Job) -> bool:
  """Checks location filters, giving absolute priority to location_allow_terms."""
  location = (job.location or "").lower()
  filters = settings.filters

  is_allowed = bool(filters.location_allow_terms and any(has_word(allow, location) for allow in filters.location_allow_terms))

  is_excluded = bool(filters.location_exclude_terms and any(has_word(ex, location) for ex in filters.location_exclude_terms))

  is_missing_required = bool(filters.location_require_terms and not any(has_word(req, location) for req in filters.location_require_terms))

  return is_allowed or (not is_excluded and not is_missing_required)


def is_job_remote(job: Job) -> bool:
  """Checks if the job is remote based on attribute or description keywords."""
  is_flagged_remote = job.remote is True

  search_text = f"{job.title or ''} {job.location or ''} {job.description or ''}"

  has_remote_keyword = bool(settings.filters.remote_keywords and any(has_word(kw, search_text) for kw in settings.filters.remote_keywords))

  return is_flagged_remote or has_remote_keyword


def is_recent_enough(job: Job) -> bool:
  """Checks if the job posting is within the max age days filter."""
  has_no_date = not job.posted
  if has_no_date:
    return True

  try:
    posted_date = datetime.datetime.strptime(str(job.posted)[:10], "%Y-%m-%d").date()
    age_days = (datetime.datetime.now(datetime.UTC).date() - posted_date).days
    is_within_age_limit = age_days <= settings.filters.max_age_days

    return is_within_age_limit
  except ValueError, TypeError:
    return True


def count_stack_hits(job: Job) -> int:
  """Counts how many stack keywords are present in the job title and description."""
  filters = settings.filters
  if not filters.stack_keywords:
    return 0

  search_text = f"{job.title or ''} {job.description or ''}"
  return sum(1 for kw in filters.stack_keywords if has_word(kw, search_text))


def has_required_stack(job: Job) -> bool:
  """Checks if the job description contains the required stack keywords."""
  filters = settings.filters

  no_stack_required = filters.min_stack_hits <= 0 or not filters.stack_keywords

  has_enough_hits = count_stack_hits(job) >= filters.min_stack_hits

  return no_stack_required or has_enough_hits


def passes_all_filters(job: Job) -> bool:
  """Master function to run a job through all active filters."""
  is_remote_valid = not settings.filters.require_remote or is_job_remote(job)

  return is_remote_valid and is_valid_title(job) and is_valid_company(job) and is_valid_location(job) and is_recent_enough(job) and has_required_stack(job)
