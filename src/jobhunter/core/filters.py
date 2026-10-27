import datetime
import re

from jobhunter.core.settings import settings
from jobhunter.models import Job


def has_word(keyword: str, text: str) -> bool:
  """Checks if a keyword exists in the text as a whole word, ignoring case."""
  if not text or not keyword:
    return False
  pattern = rf"(?<![a-z0-9]){re.escape(keyword.lower())}(?![a-z0-9])"
  return bool(re.search(pattern, text.lower()))


def is_valid_title(job: Job) -> bool:
  """Checks if the job title passes the include/exclude filters."""
  title = (job.title or "").lower()
  filters = settings.filters

  return not (
    (filters.title_exclude and any(has_word(ex, title) for ex in filters.title_exclude))
    or (filters.title_include and not any(has_word(inc, title) for inc in filters.title_include))
  )


def is_valid_company(job: Job) -> bool:
  """Checks if the job company passes the exclude filters."""
  company = (job.company or "").lower()
  return not any(has_word(ex, company) for ex in settings.filters.company_exclude)


def is_valid_location(job: Job) -> bool:
  """Checks location filters, giving absolute priority to location_allow_terms with inline conditions."""
  location = (job.location or "").lower()
  filters = settings.filters

  if filters.location_allow_terms and any(has_word(allow, location) for allow in filters.location_allow_terms):
    return True
  if filters.location_exclude_terms and any(has_word(ex, location) for ex in filters.location_exclude_terms):
    return False
  if filters.location_require_terms:
    return any(has_word(req, location) for req in filters.location_require_terms)

  return True


def is_job_remote(job: Job) -> bool:
  """Checks if the job is remote based on the job's remote attribute and description keywords."""
  if job.remote is True:
    return True

  search_text = f"{job.title or ''} {job.location or ''} {job.description or ''}"
  return any(has_word(kw, search_text) for kw in settings.filters.remote_keywords)


def is_recent_enough(job: Job) -> bool:
  """Checks if the job posting is within the max age days filter."""
  if not job.posted:
    return True

  try:
    posted_date = datetime.datetime.strptime(job.posted[:10], "%Y-%m-%d").date()
    age = (datetime.datetime.now(datetime.UTC).date() - posted_date).days
    return age <= settings.filters.max_age_days
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
  if filters.min_stack_hits <= 0 or not filters.stack_keywords:
    return True

  hits = count_stack_hits(job)

  return hits >= filters.min_stack_hits


def passes_all_filters(job: Job) -> bool:
  """Master function to run a job through all active filters."""
  is_remote_valid = not settings.filters.require_remote or is_job_remote(job)

  return is_remote_valid and all(
    (
      is_valid_title(job),
      is_valid_company(job),
      is_valid_location(job),
      has_required_stack(job),
      is_recent_enough(job),
    )
  )
