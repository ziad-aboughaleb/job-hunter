import datetime
import re

from jobhunter.core.settings import settings
from jobhunter.models import Job


def has_word(keyword: str, text: str) -> bool:
  """Checks if a keyword exists in the text as a whole word, ignoring case."""
  pattern = rf"(?<![a-z0-9]){re.escape(keyword.lower())}(?![a-z0-9])"

  return bool(re.search(pattern, text.lower()))


def is_valid_title(job: Job) -> bool:
  """Checks if the job title passes the include/exclude filters."""
  title = job.title.lower()
  filters = settings.filters

  return not (
    (filters.title_exclude and any(has_word(ex, title) for ex in filters.title_exclude))
    or (filters.title_include and not any(has_word(inc, title) for inc in filters.title_include))
  )


def is_valid_company(job: Job) -> bool:
  """Checks if the job company passes the exclude filters."""
  company = job.company.lower()

  return not any(has_word(ex, company) for ex in settings.filters.company_exclude)


def is_valid_location(job: Job) -> bool:
  """Checks if the job location passes the include/exclude filters."""
  location = job.location.lower()
  filters = settings.filters

  return not (
    (filters.location_exclude_terms and any(has_word(ex, location) for ex in filters.location_exclude_terms))
    or (filters.location_require_terms and not any(has_word(req, location) for req in filters.location_require_terms))
  )


def is_job_remote(job: Job) -> bool:
  """Checks if the job is remote based on the job's remote attribute and description keywords."""
  if job.remote is True:
    return True

  search_text = f"{job.title} {job.location} {job.description}"
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


def has_required_stack(job: Job) -> bool:
  """Checks if the job description contains the required stack keywords."""
  filters = settings.filters
  if filters.min_stack_hits <= 0 or not filters.stack_keywords:
    return True

  search_text = f"{job.title} {job.description}"
  hits = sum(1 for kw in filters.stack_keywords if has_word(kw, search_text))

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
