import logging
from typing import Any

from jobhunter.core.logger import console
from jobhunter.core.paths import CONFIG_PATH, read, write
from jobhunter.sources import SOURCES
from jobhunter.sources.base import SlugStatus

logger = logging.getLogger(__name__)


def build_prune_tasks(raw_config: dict, source_name: str | None) -> dict[str, list[str]]:
  """Resolves and builds the list of company slugs to be checked from the config."""
  logger.info("Building prune tasks...")

  companies = raw_config.get("companies", {})

  if not companies:
    logger.info("No companies found in config.json.")
    return {}

  target_sources = {}
  for name, slugs in companies.items():
    if source_name and name != source_name:
      continue

    source = SOURCES.get(name)
    if not source:
      logger.warning(f"Source '{name}' not found in SOURCES. Skipping.")
      console.print(f"  [yellow]⚠ Notice: Source '{name}' not found in SOURCES. Skipping.[/yellow]")
      continue

    if getattr(source, "is_aggregator", False):
      continue

    target_sources[name] = slugs

  return target_sources


def validate_source_slugs(source: Any, slugs: list[str]) -> tuple[list[str], int]:
  """Tests each slug via HTTP and returns the valid ones alongside the removed count."""
  valid_slugs = []
  removed_count = 0

  logger.info(f"Starting prune check for source: {source.name}")
  console.print(f"\n[cyan]Checking [bold]{source.name}[/bold] boards ({len(slugs)} slugs)...[/cyan]")

  for slug in slugs:
    status = source.validate_slug(slug)

    if status is SlugStatus.VALID:
      valid_slugs.append(slug)
      console.print(f"  [green]✔ {slug}[/green]")

    elif status is SlugStatus.INVALID:
      removed_count += 1
      logger.info(f"Removing invalid slug '{slug}' from {source.name}")
      console.print(f"  [red]✖ Removing broken slug: {slug}[/red]")

    else:
      valid_slugs.append(slug)
      logger.warning(f"Could not definitively verify slug '{slug}' for {source.name}. Keeping it.")
      console.print(f"  [yellow]⚠ Couldn't verify: {slug} (Keeping to be safe)[/yellow]")

  return valid_slugs, removed_count


def execute_prune_checks(target_sources: dict[str, list[str]]) -> tuple[dict[str, list[str]], int]:
  """Executes the prune validation loop across target sources."""
  logger.info("Executing prune validation loop...")
  new_companies = {}
  total_removed = 0

  for name, slugs in target_sources.items():
    source = SOURCES[name]
    valid_slugs, removed = validate_source_slugs(source, slugs)

    new_companies[name] = valid_slugs
    total_removed += removed

  return new_companies, total_removed


def save_prune_results(raw_config: dict, new_companies: dict, removed_count: int, write_flag: bool):
  """Merges the pruned company list back into config and persists to disk if requested."""
  for name, slugs in new_companies.items():
    raw_config["companies"][name] = slugs

  if write_flag:
    write(CONFIG_PATH / "config.json", raw_config)
    logger.info(f"Successfully pruned {removed_count} broken slugs from config.json.")
    console.print(f"\n[bold green]Successfully pruned {removed_count} broken slugs and saved config.json![/bold green]")
  else:
    logger.info(f"Dry run complete. Found {removed_count} broken slugs.")
    console.print(f"\n[yellow]Found {removed_count} broken slugs. Run with --write to actually remove them from your config.[/yellow]")


def main(write_flag: bool = False, source_name: str | None = None):
  """Orchestrates the company slug pruning pipeline."""
  logger.info("Starting prune pipeline run.")
  console.print("[bold cyan]Pruning broken company slugs from config.json...[/bold cyan]")

  raw_config = read(CONFIG_PATH / "config.json", dict)

  tasks = build_prune_tasks(raw_config, source_name)
  if not tasks:
    logger.warning("No valid company slugs found to prune.")
    console.print("[yellow]No valid company slugs found to prune.[/yellow]")
    return

  new_companies, removed_count = execute_prune_checks(tasks)

  if removed_count == 0:
    logger.info("Prune complete. No broken slugs found.")
    console.print("\n[green]All checked company slugs are valid! No pruning needed.[/green]")
    return

  save_prune_results(raw_config, new_companies, removed_count, write_flag)

  logger.info("Prune pipeline finished.")
