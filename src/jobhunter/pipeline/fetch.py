import concurrent.futures

from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Column

from jobhunter.core.filters import count_stack_hits, passes_all_filters
from jobhunter.core.logger import console, get_logger
from jobhunter.core.settings import settings
from jobhunter.core.state import load_seen, save_candidates
from jobhunter.models import Candidate, Job
from jobhunter.sources import SOURCES

logger = get_logger(__name__, log_to_console=False)


def main(source_name: str | None, no_aggregators: bool = False, ignore_seen: bool = False):
  """Fetches jobs from all configured sources and saves new candidates to the state."""
  logger.info("Starting job fetch pipeline...")
  console.print("[bold cyan]Fetching jobs from configured sources...[/bold cyan]")

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

  if not tasks:
    logger.warning("No active sources/companies found to scrape.")
    console.print("[yellow]No active sources/companies found to scrape.[/yellow]")
    return

  fetched_jobs: list[Job] = []
  max_workers = settings.limits.fetch_workers

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

  seen_data = load_seen()
  save_candidates([])

  new_passing_jobs = []
  skipped_seen = 0
  skipped_filters = 0

  for job in fetched_jobs:
    unique_id = f"{job.source}:{job.board}:{job.job_id or job.url}"

    if unique_id in seen_data and not ignore_seen:
      skipped_seen += 1
      continue

    if passes_all_filters(job):
      new_passing_jobs.append(job)
    else:
      skipped_filters += 1

  priority_companies = {c.lower() for c in settings.filters.company_priority}

  scored_jobs = [(job, (job.company or "").lower() in priority_companies, count_stack_hits(job)) for job in new_passing_jobs]

  scored_jobs.sort(key=lambda item: (item[1], item[2]), reverse=True)

  sorted_passing_jobs = [item[0] for item in scored_jobs]

  max_candidates = settings.limits.max_candidates_per_run
  final_passing_jobs = []
  non_priority_count = 0

  for job in sorted_passing_jobs:
    is_priority = (job.company or "").lower() in priority_companies
    if is_priority:
      final_passing_jobs.append(job)
    else:
      if non_priority_count < max_candidates:
        final_passing_jobs.append(job)
        non_priority_count += 1

  cut_over_cap = len(sorted_passing_jobs) - len(final_passing_jobs)

  final_candidates = []

  for i, job in enumerate(final_passing_jobs, start=1):
    ref = f"J{i}"
    is_priority = (job.company or "").lower() in priority_companies
    hits = count_stack_hits(job)

    candidate = Candidate.from_job(job, ref=ref, priority=is_priority, stack_hits=hits)
    final_candidates.append(candidate)

  if final_candidates:
    save_candidates(final_candidates)

  logger.info(
    f"Fetch summary — Raw: {len(fetched_jobs)}, "
    f"Skipped Seen: {skipped_seen}, "
    f"Failed Filters: {skipped_filters}, "
    f"Cut Over Cap: {cut_over_cap}, "
    f"New Candidates: {len(final_candidates)}"
  )

  console.print("\n[bold]Fetch Summary[/bold]")
  console.print("──────────────────────────────")
  console.print(f"Total raw jobs  : [cyan]{len(fetched_jobs)}[/cyan]")
  console.print(f"Skipped (sent)  : [yellow]{skipped_seen}[/yellow]")
  console.print(f"Failed filters  : [magenta]{skipped_filters}[/magenta]")
  console.print(f"Cut over cap    : [yellow]{cut_over_cap}[/yellow]")
  console.print(f"New candidates  : [bold green]{len(final_candidates)}[/bold green]")
  console.print("──────────────────────────────\n")
