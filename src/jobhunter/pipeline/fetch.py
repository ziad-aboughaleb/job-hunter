import concurrent.futures

from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Column

from jobhunter.core.filters import passes_all_filters
from jobhunter.core.logger import console, get_logger
from jobhunter.core.settings import settings
from jobhunter.core.state import load_candidates, load_seen, save_candidates
from jobhunter.models import Job
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
  candidates = load_candidates()
  pending_ids = {f"{c.source}:{c.board}:{c.job_id or c.url}" for c in candidates}

  new_passing_jobs = []
  skipped_seen = 0
  skipped_pending = 0
  skipped_filters = 0

  for job in fetched_jobs:
    unique_id = f"{job.source}:{job.board}:{job.job_id or job.url}"

    if unique_id in seen_data and not ignore_seen:
      skipped_seen += 1
      continue

    if unique_id in pending_ids:
      skipped_pending += 1
      continue

    pending_ids.add(unique_id)

    if passes_all_filters(job):
      new_passing_jobs.append(job)
    else:
      skipped_filters += 1

  if new_passing_jobs:
    candidates.extend(new_passing_jobs)
    save_candidates(candidates)

  logger.info(
    f"Fetch summary — Raw: {len(fetched_jobs)}, "
    f"Skipped Seen: {skipped_seen}, "
    f"Skipped Pending: {skipped_pending}, "
    f"Failed Filters: {skipped_filters}, "
    f"New Candidates: {len(new_passing_jobs)}"
  )

  console.print("\n[bold]Fetch Summary[/bold]")
  console.print("──────────────────────────────")
  console.print(f"Total raw jobs  : [cyan]{len(fetched_jobs)}[/cyan]")
  console.print(f"Skipped (sent)  : [yellow]{skipped_seen}[/yellow]")
  console.print(f"Skipped (pend)  : [yellow]{skipped_pending}[/yellow]")
  console.print(f"Failed filters  : [magenta]{skipped_filters}[/magenta]")
  console.print(f"New candidates  : [bold green]{len(new_passing_jobs)}[/bold green]")
  console.print("──────────────────────────────\n")
