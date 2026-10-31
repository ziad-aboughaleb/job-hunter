import logging
import sys
from pathlib import Path
from typing import Annotated

import typer

from jobhunter.core.logger import console, setup_logging
from jobhunter.pipeline import evaluate, fetch, send
from jobhunter.tools import discover, init, prompt, prune

app = typer.Typer(
  help="JobHunter - Automated job scraping and filtering pipeline.",
  no_args_is_help=True,
  context_settings={"help_option_names": ["-h", "--help"]},
)

# Reusable CLI Options with enhanced documentation
SourceOpt = Annotated[str | None, typer.Option("--source", "-s", help="Specific ATS source or aggregator to fetch from (e.g., 'greenhouse', 'remotive').")]
NoAggOpt = Annotated[bool, typer.Option("--no-aggregators", help="Skip aggregator boards and only scrape direct company ATS boards.")]
IgnoreSeenOpt = Annotated[bool, typer.Option("--ignore-seen", help="Ignore the 'seen' cache and fetch all jobs regardless of previous processing.")]
LimitOpt = Annotated[int | None, typer.Option("--limit", "-l", help="Override the maximum number of candidates to process (bypasses config.json limit).")]
WriteOpt = Annotated[bool, typer.Option("--write", "-w", help="Persist discovered/pruned companies by writing directly to config.json.")]
JobUidOpt = Annotated[str | None, typer.Option("--job", "-j", help="Evaluate only a specific candidate by their exact Job UID.")]
DryRunOpt = Annotated[bool, typer.Option("--dry-run", help="Dispatch alerts without modifying the local 'seen' cache or state files.")]


@app.command("init", help="Scaffolds a new JobHunter workspace by downloading default templates and docs.")
def init_workspace(dir: Annotated[Path, typer.Argument(help="Target directory to initialize the JobHunter workspace.")] = Path(".")):
  init.main(dir=dir)


@app.command("run", help="Run the full pipeline (fetch -> evaluate -> send).")
def run_all(
  source: SourceOpt = None,
  no_aggregators: NoAggOpt = False,
  ignore_seen: IgnoreSeenOpt = False,
  limit: LimitOpt = None,
  dry_run: DryRunOpt = False,
):
  fetch.main(source_name=source, no_aggregators=no_aggregators, ignore_seen=ignore_seen, limit=limit)
  evaluate.main(limit=limit)
  send.main(dry_run=dry_run)


@app.command("fetch", help="Scrape and filter jobs from configured boards.")
def fetch_jobs(
  source: SourceOpt = None,
  no_aggregators: NoAggOpt = False,
  ignore_seen: IgnoreSeenOpt = False,
  limit: LimitOpt = None,
):
  fetch.main(source_name=source, no_aggregators=no_aggregators, ignore_seen=ignore_seen, limit=limit)


@app.command("evaluate", help="Score and evaluate pending candidates using AI.")
def evaluate_jobs(
  job: JobUidOpt = None,
  limit: LimitOpt = None,
):
  evaluate.main(job_uid=job, limit=limit)


@app.command("send", help="Dispatch passing job evaluations to Telegram.")
def send_jobs(dry_run: DryRunOpt = False):
  send.main(dry_run=dry_run)


@app.command("discover", help="Discover and validate new company boards via search engines.")
def discover_boards(
  write: WriteOpt = False,
  source: SourceOpt = None,
  titles: Annotated[str | None, typer.Option("--titles", "-t", help="Comma-separated list of job titles to search for (e.g., 'engineer,developer').")] = None,
):
  discover.main(write_flag=write, source_name=source, titles_override=titles)


@app.command("prune", help="Validate and prune broken company endpoints from config.json.")
def prune_companies(write: WriteOpt = False, source: SourceOpt = None):
  prune.main(write_flag=write, source_name=source)


@app.command("prompt", help="Prints the compiled AI evaluation system prompt for review.")
def show_prompt():
  prompt.main()


def main():
  """Entry point wrapper to catch global exceptions."""
  setup_logging(level="INFO")

  try:
    app()
  except KeyboardInterrupt:
    console.print("\n[yellow]Aborted by user.[/yellow]")
    sys.exit(1)
  except Exception as e:
    logger = logging.getLogger(__name__)
    logger.exception(f"Fatal error: {e}")
    console.print(f"[bold red]Fatal error: {e}[/bold red]")
    sys.exit(1)
