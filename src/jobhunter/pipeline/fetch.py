import concurrent.futures

from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Column

from jobhunter.core.filters import count_stack_hits, passes_all_filters
from jobhunter.core.logger import console, get_logger
from jobhunter.core.paths import DATA_PATH, read, write
from jobhunter.core.settings import settings
from jobhunter.models import Candidate, Job
from jobhunter.sources import SOURCES

logger = get_logger(__name__, log_to_console=False)


def build_fetch_tasks(source_name: str | None, no_aggregators: bool) -> list[tuple]:
  """Generates a list of (source, slug) tuples to be scraped."""
  logger.info("Building fetch tasks...")
  tasks = []

  for name, source in SOURCES.items():
    if source_name and name != source_name:
      continue

    is_aggregator = getattr(source, "is_aggregator", False)

    if is_aggregator and not no_aggregators:
      tasks.append((source, ""))
    else:
      slugs = settings.companies.get(name, [])
      for slug in slugs:
        tasks.append((source, slug))

  logger.info(f"Generated {len(tasks)} fetch tasks.")
  return tasks


def execute_fetch_tasks(tasks: list[tuple]) -> list[Job]:
  """Executes the scraping tasks concurrently with a Rich progress bar."""
  fetched_jobs: list[Job] = []
  max_workers = settings.limits.fetch_workers

  logger.info(f"Executing fetch tasks with {max_workers} workers...")
  console.print("[bold cyan]Fetching jobs from configured sources...[/bold cyan]")

  with Progress(
    SpinnerColumn("dots", style="cyan"),
    TextColumn("{task.description}", table_column=Column(ratio=1)),
    TextColumn("[dim]{task.completed}/{task.total}[/dim]"),
    BarColumn(bar_width=24, style="dim cyan", complete_style="green", finished_style="bold green"),
    TaskProgressColumn(),
    expand=True,
    console=console,
  ) as progress:
    fetch_task = progress.add_task("[cyan]Starting fetch...", total=len(tasks))

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
      future_to_name = {executor.submit(source.execute_scraper, slug): f"{source.name}:{slug}" if slug else source.name for source, slug in tasks}

      for future in concurrent.futures.as_completed(future_to_name):
        name = future_to_name[future]
        try:
          result = future.result()
          if result:
            fetched_jobs.extend(result)

          progress.update(fetch_task, advance=1, description=f"[cyan]Fetching... [dim](Finished {name})[/dim]")
        except Exception as e:
          logger.exception(f"Error fetching {name}: {e}")
          progress.console.print(f"[red]Error fetching {name}: {e}[/red]")
          progress.update(fetch_task, advance=1)

    progress.update(fetch_task, description="[bold green]Fetch complete![/bold green]")

  logger.info(f"Successfully fetched {len(fetched_jobs)} raw jobs.")
  return fetched_jobs


def filter_and_dedupe_jobs(fetched_jobs: list[Job], ignore_seen: bool) -> tuple[list[Job], int, int, int]:
  """Removes previously seen jobs, cross-source duplicates, and jobs failing filters."""
  logger.info("Filtering and deduplicating jobs...")
  console.print("[dim cyan]Filtering and deduplicating jobs...[/dim cyan]")

  seen_data = read(DATA_PATH / "seen.json", dict)

  new_passing_jobs = []
  skipped_seen = 0
  skipped_dupes = 0
  skipped_filters = 0

  run_seen_roles = set()

  for job in fetched_jobs:
    unique_id = f"{job.source}:{job.board}:{job.job_id or job.url}"

    if unique_id in seen_data and not ignore_seen:
      skipped_seen += 1
      continue

    company = (job.company or "Unknown").strip().lower()
    title = (job.title or "Unknown").strip().lower()
    location = (job.location or "Unknown").strip().lower()
    role_key = f"{company}:{title}:{location}"

    if role_key in run_seen_roles and not ignore_seen:
      skipped_dupes += 1
      continue

    run_seen_roles.add(role_key)

    if passes_all_filters(job):
      new_passing_jobs.append(job)
    else:
      skipped_filters += 1

  logger.info(f"Filtering complete: {len(new_passing_jobs)} passed, {skipped_seen} skipped (seen), {skipped_dupes} dupes, {skipped_filters} failed filters.")
  return new_passing_jobs, skipped_seen, skipped_dupes, skipped_filters


def score_and_sort_jobs(jobs: list[Job]) -> list[Job]:
  """Scores jobs based on priority and stack hits, sorting the best to the top."""
  logger.info("Scoring and sorting passing jobs...")
  console.print("[dim cyan]Scoring and sorting candidates...[/dim cyan]")

  priority_companies = {c.lower() for c in settings.filters.company_priority}

  scored_jobs = [(job, (job.company or "").lower() in priority_companies, count_stack_hits(job)) for job in jobs]

  # Sort primarily by Priority Company (True/False), then by Stack Hits (highest to lowest)
  scored_jobs.sort(key=lambda item: (item[1], item[2]), reverse=True)

  return [item[0] for item in scored_jobs]


def cap_and_format_candidates(sorted_jobs: list[Job], limit: int | None = None) -> tuple[list[Candidate], int]:
  """Enforces the max candidate limit and converts Jobs into final Candidates."""
  logger.info("Enforcing limits and generating final candidates...")
  console.print("[dim cyan]Enforcing candidate limits...[/dim cyan]")

  priority_companies = {c.lower() for c in settings.filters.company_priority}
  max_candidates = limit or settings.limits.max_candidates_per_run

  final_passing_jobs = []
  non_priority_count = 0

  for job in sorted_jobs:
    is_priority = (job.company or "").lower() in priority_companies
    if is_priority:
      final_passing_jobs.append(job)
    elif non_priority_count < max_candidates:
      final_passing_jobs.append(job)
      non_priority_count += 1

  cut_over_cap = len(sorted_jobs) - len(final_passing_jobs)
  final_candidates = []

  for i, job in enumerate(final_passing_jobs, start=1):
    ref = f"J{i}"
    is_priority = (job.company or "").lower() in priority_companies
    hits = count_stack_hits(job)

    candidate = Candidate.from_job(job, ref=ref, priority=is_priority, stack_hits=hits)
    final_candidates.append(candidate)

  logger.info(f"Generated {len(final_candidates)} candidates. Cut {cut_over_cap} jobs over the cap.")

  return final_candidates, cut_over_cap


def main(source_name: str | None = None, no_aggregators: bool = False, ignore_seen: bool = False, limit: int | None = None):
  """Orchestrates the job fetching, filtering, and candidate generation pipeline."""
  logger.info("Starting job fetch pipeline...")

  # 1. Setup
  tasks = build_fetch_tasks(source_name, no_aggregators)
  if not tasks:
    logger.warning("No active sources/companies found to scrape.")
    console.print("[yellow]No active sources/companies found to scrape.[/yellow]")
    return

  # 2. Extract
  fetched_jobs = execute_fetch_tasks(tasks)

  # 3. Filter
  passing_jobs, skipped_seen, skipped_dupes, skipped_filters = filter_and_dedupe_jobs(fetched_jobs, ignore_seen)

  # 4. Score
  sorted_jobs = score_and_sort_jobs(passing_jobs)

  # 5. Cap & Format
  final_candidates, cut_over_cap = cap_and_format_candidates(sorted_jobs, limit)

  # 6. Save
  if final_candidates:
    write(DATA_PATH / "candidates.json", final_candidates)
    logger.info(f"Successfully saved {len(final_candidates)} candidates to disk.")

  # 7. Report
  logger.info(f"Fetch pipeline completed. Raw: {len(fetched_jobs)} | Seen: {skipped_seen} | Dupe: {skipped_dupes} | Failed Filters: {skipped_filters} | Cut: {cut_over_cap} | Candidates: {len(final_candidates)}")

  console.print("\n[bold]Fetch Summary[/bold]")
  console.print("──────────────────────────────")
  console.print(f"Total raw jobs  : [cyan]{len(fetched_jobs)}[/cyan]")
  console.print(f"Skipped (seen)  : [yellow]{skipped_seen}[/yellow]")
  console.print(f"Skipped (dupe)  : [yellow]{skipped_dupes}[/yellow]")
  console.print(f"Failed filters  : [magenta]{skipped_filters}[/magenta]")
  console.print(f"Cut over cap    : [yellow]{cut_over_cap}[/yellow]")
  console.print(f"New candidates  : [bold green]{len(final_candidates)}[/bold green]")
  console.print("──────────────────────────────\n")
