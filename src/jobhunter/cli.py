import sys

import typer

from jobhunter.pipeline import evaluate, fetch, send
from jobhunter.tools import discover, prune

app = typer.Typer(
  help="JobHunter - Automated job scraping and filtering pipeline.",
  no_args_is_help=True,
  context_settings={"help_option_names": ["-h", "--help"]},
)


@app.command("run", help="Run the full pipeline (fetch -> evaluate -> send)")
def run_all(no_boards: bool = typer.Option(False, "--no-boards", help="Skip aggregator boards")):
  fetch.main(no_boards=no_boards)
  evaluate.main()
  send.main()


@app.command("fetch", help="Fetch jobs from configured boards")
def fetch_jobs(no_boards: bool = typer.Option(False, "--no-boards", help="Skip aggregator boards")):
  fetch.main(no_boards=no_boards)


@app.command("evaluate", help="Score and evaluate candidates")
def evaluate_jobs():
  evaluate.main()


@app.command("send", help="Send passing jobs to Telegram")
def send_jobs():
  send.main()


@app.command("discover", help="Discover and validate new company boards")
def discover_boards():
  discover.main()


@app.command("prune", help="Prune expired jobs from state/seen files")
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
