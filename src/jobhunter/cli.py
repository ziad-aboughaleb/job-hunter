import sys

import typer

from jobhunter.pipeline import evaluate, fetch, send
from jobhunter.tools import discover, prune

app = typer.Typer(
  help="JobHunter - Automated job scraping and filtering pipeline.",
  no_args_is_help=True,
  context_settings={"help_option_names": ["-h", "--help"]},
)

SourceOpt = typer.Option(None, "--source", "-s", help="Specific source to fetch from")
NoAggOpt = typer.Option(False, "--no-aggregators", help="Skip aggregator boards")
IgnoreSeenOpt = typer.Option(False, "--ignore-seen", help="Ignore seen jobs and fetch all")


@app.command("run", help="Run the full pipeline (fetch -> evaluate -> send)")
def run_all(source: str | None = SourceOpt, no_aggregators: bool = NoAggOpt, ignore_seen: bool = IgnoreSeenOpt):
  fetch.main(source_name=source, no_aggregators=no_aggregators, ignore_seen=ignore_seen)
  evaluate.main()
  send.main()


@app.command("fetch", help="Fetch jobs from configured boards")
def fetch_jobs(source: str | None = SourceOpt, no_aggregators: bool = NoAggOpt, ignore_seen: bool = IgnoreSeenOpt):
  fetch.main(source_name=source, no_aggregators=no_aggregators, ignore_seen=ignore_seen)


@app.command("evaluate", help="Score and evaluate candidates")
def evaluate_jobs():
  evaluate.main()


@app.command("send", help="Send passing jobs to Telegram")
def send_jobs():
  send.main()


@app.command("discover", help="Discover and validate new company boards")
def discover_boards():
  discover.main()


@app.command("prune", help="Prune broken company entries from config/config.json")
def prune_state():
  prune.main()


def main():
  """Entry point wrapper to catch global exceptions."""
  try:
    app()
  except KeyboardInterrupt:
    typer.secho("\nAborted by user.", fg=typer.colors.YELLOW)
    sys.exit(1)
  except Exception as e:
    typer.secho(f"\nFatal error: {e}", fg=typer.colors.RED, err=True)
    sys.exit(1)
