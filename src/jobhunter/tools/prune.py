from jobhunter.core.logger import console, get_logger
from jobhunter.core.state import load_config, save_config
from jobhunter.sources import SOURCES
from jobhunter.sources.base import SlugStatus

logger = get_logger(__name__, log_to_console=False)


def main(write: bool = False, source_name: str | None = None):
  """Prunes definitively broken or non-existent company slugs from config.json."""
  logger.info("Starting prune process...")
  console.print("[bold cyan]Pruning broken company slugs from config.json...[/bold cyan]")

  raw_config = load_config()
  companies = raw_config.get("companies", {})

  if not companies:
    logger.info("No companies found in config.json. Nothing to prune.")
    console.print("[yellow]No companies found in config.json.[/yellow]")
    return

  removed_count = 0
  new_companies = {}

  for name, slugs in companies.items():
    if source_name and name != source_name:
      continue

    source = SOURCES.get(name)

    if not source:
      logger.warning(f"Source '{name}' not found in SOURCES. Skipping.")
      console.print(f"[red]Source '{name}' not found. Skipping.[/red]")
      continue

    if getattr(source, "is_aggregator", False):
      continue

    valid_slugs = []

    logger.info(f"Starting prune check for source: {name}")
    console.print(f"\n[cyan]Checking [bold]{name}[/bold] boards ({len(slugs)} slugs)...[/cyan]")

    for slug in slugs:
      status = source.validate_slug(slug)

      if status is SlugStatus.VALID:
        valid_slugs.append(slug)
        console.print(f"  [green]✔ {slug}[/green]")

      elif status is SlugStatus.INVALID:
        removed_count += 1
        logger.info(f"Removing invalid slug '{slug}' from {name}")
        console.print(f"  [red]✖ Removing broken slug: {slug}[/red]")

      else:
        valid_slugs.append(slug)
        logger.warning(f"Could not definitively verify slug '{slug}' for {name}. Keeping it.")
        console.print(f"  [dim yellow]? Couldn't verify: {slug} (Keeping to be safe)[/dim yellow]")

    new_companies[name] = valid_slugs

  if removed_count == 0:
    console.print("\n[green]All checked company slugs are valid! No pruning needed.[/green]")
    return

  raw_config["companies"] = new_companies

  if write:
    save_config(raw_config)
    logger.info(f"Successfully pruned {removed_count} broken slugs from config.json.")
    console.print(f"\n[bold green]Successfully pruned {removed_count} broken slugs and saved config.json![/bold green]")
  else:
    console.print(f"\n[yellow]Found {removed_count} broken slugs. Run with --write to actually remove them from your config.[/yellow]")
