import sys
from typing import Annotated

import typer

from jobhunter.core.logger import console, setup_logging
from jobhunter.pipeline import evaluate, fetch, send
from jobhunter.tools import discover, prompt, prune

app = typer.Typer(
  help="JobHunter - Automated job scraping and filtering pipeline.",
  no_args_is_help=True,
  context_settings={"help_option_names": ["-h", "--help"]},
)

# 1. Use Annotated for reusable CLI parameters
SourceOpt = Annotated[str | None, typer.Option("--source", "-s", help="Specific source to fetch from")]
NoAggOpt = Annotated[bool, typer.Option("--no-aggregators", help="Skip aggregator boards")]
IgnoreSeenOpt = Annotated[bool, typer.Option("--ignore-seen", help="Ignore seen jobs and fetch all")]
LimitOpt = Annotated[int | None, typer.Option("--limit", "-l", help="Overrides max_candidates limit in config.json")]
WriteOpt = Annotated[bool, typer.Option("--write", "-w", help="Write changes to config.json")]


@app.command("run", help="Run the full pipeline (fetch -> evaluate -> send)")
def run_all(
  source: SourceOpt = None,
  no_aggregators: NoAggOpt = False,
  ignore_seen: IgnoreSeenOpt = False,
  limit: LimitOpt = None,
):
  fetch.main(source_name=source, no_aggregators=no_aggregators, ignore_seen=ignore_seen, limit=limit)
  evaluate.main()
  send.main()


@app.command("fetch", help="Fetch jobs from configured boards")
def fetch_jobs(
  source: SourceOpt = None,
  no_aggregators: NoAggOpt = False,
  ignore_seen: IgnoreSeenOpt = False,
  limit: LimitOpt = None,
):
  fetch.main(source_name=source, no_aggregators=no_aggregators, ignore_seen=ignore_seen, limit=limit)


@app.command("evaluate", help="Score and evaluate candidates")
def evaluate_jobs():
  evaluate.main()


@app.command("send", help="Send passing jobs to Telegram")
def send_jobs():
  send.main()


@app.command("discover", help="Discover and validate new company boards")
def discover_boards(
  write: WriteOpt = False,
  source: SourceOpt = None,
  titles: Annotated[str | None, typer.Option("--titles", "-t", help="Comma-separated list of titles to search for")] = None,
):
  discover.main(write_flag=write, source_name=source, titles_override=titles)


@app.command("prune", help="Prune broken company entries from config.json")
def prune_companies(write: WriteOpt = False, source: SourceOpt = None):
  prune.main(write_flag=write, source_name=source)


@app.command("prompt", help="Prints the AI evaluation prompt for review")
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
    console.print(f"\n[bold red]Error: {e}[/bold red]")
    sys.exit(1)
