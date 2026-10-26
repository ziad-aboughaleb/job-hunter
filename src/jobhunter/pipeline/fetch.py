import concurrent.futures

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

from jobhunter.core.filters import passes_all_filters
from jobhunter.core.settings import settings
from jobhunter.core.state import load_candidates, load_seen, save_candidates
from jobhunter.models import Job
from jobhunter.sources import SOURCES

console = Console()


def is_source_enabled(source_name: str) -> bool:
  """Checks if a source is explicitly disabled in settings.boards."""
  board_cfg = settings.boards.get(source_name)
  if isinstance(board_cfg, bool):
    return board_cfg
  if isinstance(board_cfg, dict):
    return board_cfg.get("enabled", True)
  return True


def execute_scraper(source, slug: str | None = None) -> list[Job]:
  """Runs a single scraper instance for a specific board or company."""
  if slug:
    return source.fetch(slug=slug) or []
  return source.fetch() or []


def main(no_boards: bool = False):
  tasks = []

  for name, source in SOURCES.items():
    if not is_source_enabled(name):
      continue

    is_aggregator = getattr(source, "is_aggregator", False)

    if is_aggregator:
      if not no_boards:
        tasks.append((source, None))
    else:
      slugs = settings.companies.get(name, [])
      for slug in slugs:
        tasks.append((source, slug))

  if not tasks:
    console.print("[yellow]No active sources/companies found to scrape.[/yellow]")
    return

  fetched_jobs: list[Job] = []
  max_workers = settings.limits.fetch_workers

  with Progress(
    SpinnerColumn(),
    TextColumn("[progress.description]{task.description}"),
    BarColumn(),
    TaskProgressColumn(),
    console=console,
  ) as progress:
    fetch_task = progress.add_task("[cyan]Starting fetch...", total=len(tasks))

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
      future_to_name = {executor.submit(execute_scraper, source, slug): f"{source.name}:{slug}" if slug else source.name for source, slug in tasks}

      for future in concurrent.futures.as_completed(future_to_name):
        name = future_to_name[future]
        try:
          result = future.result()
          fetched_jobs.extend(result)

          progress.update(fetch_task, advance=1, description=f"[cyan]Fetching... [dim](Finished {name})[/dim]")
        except Exception as e:
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

    if unique_id in seen_data:
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

  console.print("\n[bold]Fetch Summary[/bold]")
  console.print("──────────────────────────────")
  console.print(f"Total raw jobs  : [cyan]{len(fetched_jobs)}[/cyan]")
  console.print(f"Skipped (sent)  : [yellow]{skipped_seen}[/yellow]")
  console.print(f"Skipped (pend)  : [yellow]{skipped_pending}[/yellow]")
  console.print(f"Failed filters  : [magenta]{skipped_filters}[/magenta]")
  console.print(f"New candidates  : [bold green]{len(new_passing_jobs)}[/bold green]")
  console.print("──────────────────────────────\n")


if __name__ == "__main__":
  main()
