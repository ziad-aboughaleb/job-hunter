from rich.console import Console

from jobhunter.core.state import load_config, save_config
from jobhunter.sources import SOURCES

console = Console()


def is_valid_board(source_name: str, slug: str) -> bool:
  """Checks if an ATS slug is reachable via its public API endpoint."""
  source = SOURCES.get(source_name)

  try:
    if source is None:
      console.print(f"[red]Source '{source_name}' not found.[/red]")
      return False

    response = source.fetch(slug)
    return response is not None
  except Exception as e:
    console.print(f"[red]Error checking slug '{slug}' for source '{source_name}': {e}[/red]")
    return False


def main(write: bool = False, source_name: str | None = None):
  """Prunes broken or non-existent company slugs from config.json."""
  raw_config = load_config()
  companies = raw_config.get("companies", {})

  if not companies:
    console.print("[yellow]No companies found in config.json.[/yellow]")
    return

  removed_count = 0
  new_companies = {}

  for name, slugs in companies.items():
    valid_slugs = []
    console.print(f"\n[cyan]Checking [bold]{name}[/bold] boards ({len(slugs)} slugs)...[/cyan]")

    for slug in slugs:
      if is_valid_board(name, slug):
        valid_slugs.append(slug)
        console.print(f"  [green]✔ {slug}[/green]")
      else:
        removed_count += 1
        console.print(f"  [red]✖ Removing broken slug: {slug}[/red]")

    new_companies[name] = valid_slugs

  if removed_count == 0:
    console.print("\n[green]All company slugs are valid! No pruning needed.[/green]")
    return

  raw_config["companies"] = new_companies

  if write:
    save_config(raw_config)
    console.print(f"\n[bold green]Successfully pruned {removed_count} broken slugs and saved config.json![/bold green]")
  else:
    console.print(f"\n[yellow]Found {removed_count} broken slugs. Run with --write to remove them from your config.[/yellow]")
