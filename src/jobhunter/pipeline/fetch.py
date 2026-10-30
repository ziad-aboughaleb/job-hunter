import concurrent.futures
import logging

from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Column

from jobhunter.core.filters import count_stack_hits, passes_all_filters
from jobhunter.core.logger import console
from jobhunter.core.paths import DATA_PATH, read, write
from jobhunter.core.settings import settings
from jobhunter.models import Candidate, Job
from jobhunter.sources import SOURCES

logger = logging.getLogger(__name__)


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
  target_total = len(tasks)

  logger.info(f"Executing fetch tasks across {target_total} targets with {max_workers} workers.")
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
    fetch_task = progress.add_task("[cyan]Starting fetch...", total=target_total)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
      future_to_name = {}
      for source, slug in tasks:
        name = f"{source.name}:{slug}" if slug else source.name
        future = executor.submit(source.execute_scraper, slug)
        future_to_name[future] = name

      for future in concurrent.futures.as_completed(future_to_name):
        name = future_to_name[future]

        try:
          result = future.result(timeout=60)
          if result:
            fetched_jobs.extend(result)

          progress.update(fetch_task, advance=1, description=f"[cyan]Fetching... [dim](Finished {name})[/dim]")

        except concurrent.futures.TimeoutError:
          logger.error(f"Task for {name} timed out.")
          console.print(f"  [red]✖ Task for {name} timed out.[/red]")
          progress.update(fetch_task, advance=1)

        except Exception as e:
          logger.exception(f"Error executing fetch task for {name}: {e}")
          console.print(f"  [red]✖ Error fetching {name}: {e}[/red]")
          progress.update(fetch_task, advance=1)

    progress.update(fetch_task, description="[bold green]Fetch complete![/bold green]")

  logger.info(f"Successfully fetched {len(fetched_jobs)} raw jobs.")

  return fetched_jobs


def filter_fetch_results(jobs: list[Job], ignore_seen: bool) -> tuple[list[Job], int, int, int, int]:
  """Removes previously seen jobs, cross-source duplicates, and jobs failing filters."""
  logger.info("Filtering and deduplicating jobs...")
  console.print("[dim cyan]Filtering and deduplicating jobs...[/dim cyan]")

  raw_candidates = read(DATA_PATH / "candidates.json", list)
  seen_data = read(DATA_PATH / "seen.json", dict)

  fetched_uids = {item.get("uid") for item in raw_candidates if "uid" in item}

  skipped_pend = skipped_seen = skipped_dupes = skipped_filters = 0
  run_duped_roles = set()
  passing_jobs = []

  for job in jobs:
    if job.uid in fetched_uids:
      skipped_pend += 1
      continue

    if job.uid in seen_data and not ignore_seen:
      skipped_seen += 1
      continue

    company = (job.company or "Unknown").strip().lower()
    title = (job.title or "Unknown").strip().lower()
    location = (job.location or "Unknown").strip().lower()
    role_key = f"{company}:{title}:{location}"

    if role_key in run_duped_roles:
      skipped_dupes += 1
      continue

    run_duped_roles.add(role_key)

    if passes_all_filters(job):
      passing_jobs.append(job)
    else:
      skipped_filters += 1

  logger.info(f"Filtering complete: {len(passing_jobs)} passed, {skipped_pend} skipped (pend), {skipped_seen} skipped (seen), {skipped_dupes} dupes, {skipped_filters} failed filters.")

  return passing_jobs, skipped_pend, skipped_seen, skipped_dupes, skipped_filters


def score_fetch_results(jobs: list[Job]) -> list[Candidate]:
  """Calculates scores, sorts candidates, and converts Jobs into Candidates."""
  logger.info("Scoring and sorting passing jobs...")
  console.print("[dim cyan]Scoring and sorting candidates...[/dim cyan]")

  priority_companies = {c.lower() for c in settings.filters.company_priority}

  scored_candidates: list[Candidate] = []
  for job in jobs:
    is_priority = (job.company or "").lower() in priority_companies
    hits = count_stack_hits(job)
    candidate = Candidate.from_job(job, priority=is_priority, stack_hits=hits)
    scored_candidates.append(candidate)

  scored_candidates.sort(key=lambda c: (c.priority, c.stack_hits), reverse=True)

  return scored_candidates


def limit_fetch_results(scored_candidates: list[Candidate], limit: int | None = None) -> tuple[list[Candidate], int]:
  """Enforces the max candidate limit."""
  logger.info("Enforcing limits...")
  console.print("[dim cyan]Enforcing candidate limits...[/dim cyan]")

  max_candidates = limit or settings.limits.max_candidates_per_run

  final_candidates = []
  non_priority_count = 0

  for candidate in scored_candidates:
    if not candidate.priority:
      if non_priority_count >= max_candidates:
        continue
      non_priority_count += 1

    final_candidates.append(candidate)

  cut_over_cap = len(scored_candidates) - len(final_candidates)

  logger.info(f"Generated {len(final_candidates)} candidates. Cut {cut_over_cap} jobs over the cap.")

  return final_candidates, cut_over_cap


def save_fetch_results(final_candidates: list[Candidate]):
  """Saves finalized candidates into disk, preventing duplicate UIDs."""
  logger.info("Saving candidates...")
  console.print("[dim cyan]Saving candidates...[/dim cyan]")

  existing_candidates = read(DATA_PATH / "candidates.json", list)

  new_uids = {c.uid for c in final_candidates}
  filtered_existing = [c for c in existing_candidates if c.get("uid") not in new_uids]

  new_candidate_dicts = [c.model_dump(mode="json") for c in final_candidates]

  filtered_existing.extend(new_candidate_dicts)
  filtered_existing.sort(key=lambda x: (x.get("priority", False), x.get("stack_hits", 0)), reverse=True)

  write(DATA_PATH / "candidates.json", filtered_existing)

  logger.info(f"Successfully saved {len(final_candidates)} candidates to disk.")


def main(source_name: str | None = None, no_aggregators: bool = False, ignore_seen: bool = False, limit: int | None = None):
  """Orchestrates the job fetching pipeline."""
  logger.info("Starting job fetch pipeline run.")

  tasks = build_fetch_tasks(source_name, no_aggregators)
  if not tasks:
    logger.warning("No active sources/companies found to scrape.")
    console.print("[yellow]No active sources/companies found to scrape.[/yellow]")
    return

  fetched_jobs = execute_fetch_tasks(tasks)

  passing_jobs, skipped_pend, skipped_seen, skipped_dupes, skipped_filters = filter_fetch_results(fetched_jobs, ignore_seen)
  scored_candidates = score_fetch_results(passing_jobs)
  final_candidates, cut_over_cap = limit_fetch_results(scored_candidates, limit)

  if final_candidates:
    save_fetch_results(final_candidates)

  logger.info(f"Pipeline finished. Raw: {len(fetched_jobs)} | Pend: {skipped_pend} | Seen: {skipped_seen} | Dupe: {skipped_dupes} | Failed Filters: {skipped_filters} | Cut: {cut_over_cap} | Candidates: {len(final_candidates)}")

  console.print("\n[bold]Fetch Summary[/bold]")
  console.print("───────────────────────────────────────")
  console.print(f"Total raw jobs  : [cyan]{len(fetched_jobs)}[/cyan]")
  console.print(f"Skipped (pend)  : [yellow]{skipped_pend}[/yellow]")
  console.print(f"Skipped (seen)  : [yellow]{skipped_seen}[/yellow]")
  console.print(f"Skipped (dupe)  : [yellow]{skipped_dupes}[/yellow]")
  console.print(f"Failed filters  : [magenta]{skipped_filters}[/magenta]")
  console.print(f"Cut over cap    : [yellow]{cut_over_cap}[/yellow]")
  console.print(f"New candidates  : [bold green]{len(final_candidates)}[/bold green]")
  console.print("───────────────────────────────────────\n")
