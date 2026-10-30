import logging
import time
from collections import defaultdict
from typing import Any

from ddgs import DDGS

from jobhunter.core.logger import console
from jobhunter.core.paths import CONFIG_PATH, read, write
from jobhunter.core.settings import settings
from jobhunter.sources import SOURCES
from jobhunter.sources.base import SlugStatus

logger = logging.getLogger(__name__)

QUERY_LIMIT = 6
RETRIES = 3
BACKOFF = 1.5

HIGHLY_UNLIKELY_SLUGS = {
  "www",
  "blog",
  "careers",
  "jobs",
  "about",
  "contact",
  "press",
  "team",
  "company",
  "home",
  "privacy",
  "terms",
  "login",
  "signup",
  "support",
  "help",
  "faq",
  "legal",
  "media",
  "news",
  "events",
  "partners",
  "investors",
  "community",
  "developers",
  "resources",
  "products",
  "services",
  "solutions",
  "platform",
  "api",
  "docs",
  "documentation",
  "status",
  "security",
  "trust",
  "feedback",
  "testimonials",
  "case-studies",
  "portfolio",
  "gallery",
  "careers-page",
  "job-openings",
}


def search_with_retries(query: str, retries: int = 3, backoff: float = 1.5) -> list[dict]:
  """Fetches search results from DuckDuckGo with exponential backoff."""
  if retries <= 0:
    raise ValueError("retries must be at least 1")

  last_error: Exception | None = None

  with DDGS() as ddgs:
    for attempt in range(retries):
      try:
        return list(ddgs.text(query, max_results=30))
      except Exception as e:
        last_error = e
        if "No results found" in str(e):
          return []
        if attempt < retries - 1:
          time.sleep(backoff * (2**attempt))

  raise RuntimeError(f"Failed to fetch DDGS query '{query}' after {retries} attempts.") from last_error


def get_target_titles(titles_override: str | None) -> list[str]:
  """Determines which job titles to search for based on CLI overrides or config."""
  logger.info("Resolving target titles for discovery...")

  titles = [t.strip() for t in titles_override.split(",")] if titles_override else settings.filters.title_include

  if not titles:
    logger.warning("No target titles found in config.json or override.")
    console.print("[red]No target titles found in config.json filters.title_include.[/red]")
    return []

  target_titles = titles[:QUERY_LIMIT]
  logger.info(f"Target titles resolved: {', '.join(target_titles)}")
  console.print(f"[dim]Target titles for discovery: {', '.join(target_titles)}[/dim]")

  return target_titles


def build_discovery_tasks(source_name: str | None) -> dict[str, Any]:
  """Resolves and builds the list of valid sources for discovery suitability."""
  logger.info("Building discovery tasks...")
  active_sources = {}

  if source_name:
    if source_name not in SOURCES:
      logger.error(f"Source '{source_name}' is not configured.")
      console.print(f"[red]Error: Source '{source_name}' is not configured in your scrapers.[/red]")
      return {}

    source = SOURCES[source_name]
    if getattr(source, "is_aggregator", False):
      logger.warning(f"Source '{source_name}' is an aggregator, skipping.")
      console.print(f"[yellow]Notice: '{source_name}' is an aggregator. Discovery is only for ATS company slugs.[/yellow]")
      return {}

    if getattr(source, "domains", None):
      active_sources[source_name] = source
  else:
    for name, source in SOURCES.items():
      if not getattr(source, "is_aggregator", False) and getattr(source, "domains", None):
        active_sources[name] = source

  logger.info(f"Built {len(active_sources)} discovery tasks.")
  return active_sources


def evaluate_search_results(source: Any, results: list[dict], existing_slugs: list[str], session_slugs: set[str]) -> tuple[int, int]:
  """Processes raw search results, extracts slugs, and validates them via HTTP."""
  added_count = 0
  known_count = 0

  for result in results:
    url = result.get("href", "")
    slug = source.extract_slug(url)

    if not slug:
      if url and any(domain in url for domain in source.domains):
        logger.info(f"Ignored URL (no valid slug): {url}")
        console.print(f"  [dim yellow]⚠ Ignored URL: {url}[/dim yellow]")
      continue

    if slug in HIGHLY_UNLIKELY_SLUGS:
      continue

    if slug in existing_slugs or slug in session_slugs:
      known_count += 1
      continue

    status = source.validate_slug(slug)

    if status is SlugStatus.VALID:
      session_slugs.add(slug)
      added_count += 1
      logger.info(f"Found new valid slug for {source.name}: {slug}")
    elif status is SlugStatus.INVALID:
      console.print(f"  [dim red]✖ Not a real board: {slug}[/dim red]")
    else:
      console.print(f"  [dim yellow]? Couldn't verify: {slug}[/dim yellow]")

  return added_count, known_count


def execute_discovery_searches(active_sources: dict[str, Any], target_titles: list[str]) -> dict[str, set[str]]:
  """Runs the search queries across all domains and topics, managing rate limits."""
  logger.info("Executing search queries...")
  new_slugs: dict[str, set[str]] = defaultdict(set)

  for name, source in active_sources.items():
    existing_slugs = settings.companies.get(name, [])
    consecutive_errors = 0

    for domain in source.domains:
      for topic in target_titles:
        query = f'site:{domain} "{topic}"'

        logger.info(f"Searching {name} with query: {query}")
        console.print(f"\n[cyan]Searching [bold]{name}[/bold][/cyan] ([dim]{query}[/dim])...")

        try:
          results = search_with_retries(query, retries=RETRIES, backoff=BACKOFF)
          consecutive_errors = 0

          if not results:
            logger.info(f"No search results found for {name}.")
            console.print("  [dim]No results found.[/dim]")
            continue

          added, known = evaluate_search_results(source, results, existing_slugs, new_slugs[name])

          console.print(f"  ↳ {added} new, {known} already known.")
          logger.info(f"Finished {name}: {added} new, {known} known.")

        except Exception as e:
          consecutive_errors += 1
          logger.exception(f"Error searching {name}: {e}")
          console.print(f"[red]  ↳ Error searching {name}: {e}[/red]")

          if consecutive_errors >= 3:
            logger.warning(f"Circuit breaker triggered for {name}: 3 consecutive failures.")
            console.print("\n[bold red]Stopping early: 3 consecutive searches failed (likely rate-limited).[/bold red]")
            break

        time.sleep(BACKOFF)

      if consecutive_errors >= 3:
        break

  return new_slugs


def save_discovery_results(new_slugs: dict[str, set[str]], write_flag: bool):
  """Merges newly discovered slugs with config.json and writes to disk if requested."""
  logger.info("Saving discovery results...")

  if not any(new_slugs.values()):
    logger.info("Discovery run completed. No new slugs found.")
    console.print("\n[yellow]No new company slugs found.[/yellow]")
    return

  raw_config = read(CONFIG_PATH / "config.json", dict)
  raw_config.setdefault("companies", {})

  console.print("\n[bold]Discovery Summary:[/bold]")
  for name, slugs in new_slugs.items():
    if slugs:
      console.print(f"[green]+ {name}:[/green] {', '.join(slugs)}")
      existing = set(raw_config["companies"].get(name, []))
      existing.update(slugs)
      raw_config["companies"][name] = sorted(existing)

  if write_flag:
    write(CONFIG_PATH / "config.json", raw_config)
    logger.info("Successfully saved new company slugs to config.json.")
    console.print("\n[bold green]Successfully saved to config.json![/bold green]")
  else:
    console.print("\n[yellow]Run with --write to save these slugs to your config.[/yellow]")


def main(write_flag: bool = False, source_name: str | None = None, titles_override: str | None = None):
  """Orchestrates the discovery pipeline."""
  logger.info("Starting discovery pipeline...")
  console.print("[bold cyan]Discovering new company slugs from configured sources...[/bold cyan]")

  target_titles = get_target_titles(titles_override)
  if not target_titles:
    return

  active_sources = build_discovery_tasks(source_name)
  if not active_sources:
    return

  new_slugs = execute_discovery_searches(active_sources, target_titles)

  save_discovery_results(new_slugs, write_flag)

  logger.info("Discovery pipeline finished...")
