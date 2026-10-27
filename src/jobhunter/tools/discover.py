import time
from collections import defaultdict

from ddgs import DDGS

from jobhunter.core.logger import console, get_logger
from jobhunter.core.settings import settings
from jobhunter.core.state import load_config, save_config
from jobhunter.sources import SOURCES
from jobhunter.sources.base import SlugStatus

logger = get_logger(__name__, log_to_console=False)

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


def main(write: bool = False, source_name: str | None = None, titles_override: str | None = None):
  """Discovers new company slugs by searching for target titles on configured sources."""
  logger.info("Starting discovery run...")
  console.print("[bold cyan]Discovering new company slugs from configured sources...[/bold cyan]")

  if source_name:
    if source_name not in SOURCES:
      logger.error(f"Source '{source_name}' is not configured in your scrapers.")
      console.print(f"[red]Error: Source '{source_name}' is not configured in your scrapers.[/red]")
      return

    source = SOURCES[source_name]

    if getattr(source, "is_aggregator", False):
      logger.warning(f"Source '{source_name}' is an aggregator. Discovery is only for finding ATS company slugs.")
      console.print(f"[yellow]Notice: '{source_name}' is an aggregator. Discovery is only for finding ATS company slugs.[/yellow]")
      return

  if titles_override:
    titles = [t.strip() for t in titles_override.split(",")]
  else:
    titles = settings.filters.title_include
    if not titles:
      logger.warning("No target titles found in config.json filters.title_include.")
      console.print("[red]No target titles found in config.json filters.title_include.[/red]")
      return

  target_titles = titles[:QUERY_LIMIT]

  logger.info(f"Target titles for discovery: {', '.join(target_titles)}")
  console.print(f"[dim]Target titles for discovery: {', '.join(target_titles)}[/dim]")

  new_slugs: dict[str, set[str]] = defaultdict(set)
  found_any = False
  consecutive_errors = 0

  for name, source in SOURCES.items():
    if source_name and name != source_name:
      continue

    if getattr(source, "is_aggregator", False) or not getattr(source, "domains", None):
      continue

    for domain in source.domains:
      for topic in target_titles:
        query = f'site:{domain} "{topic}"'

        logger.info(f"Searching {name} with query: {query}")
        console.print(f"\n[cyan]Searching [bold]{name}[/bold][/cyan] ([dim]{query}[/dim])...")

        results = []

        try:
          results = search_with_retries(query, retries=RETRIES, backoff=BACKOFF)
          consecutive_errors = 0

          if not results:
            logger.info(f"No search results found for {name}.")
            console.print("  [dim]No results found.[/dim]")
            continue

          added_count = 0
          known = 0

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

            existing = settings.companies.get(name, [])

            if slug in existing or slug in new_slugs[name]:
              known += 1
              continue

            status = source.validate_slug(slug)
            if status is SlugStatus.VALID:
              new_slugs[name].add(slug)
              added_count += 1
              found_any = True
              logger.info(f"Found new valid slug for {name}: {slug}")
            elif status is SlugStatus.INVALID:
              console.print(f"  [dim red]✖ Not a real board: {slug}[/dim red]")
            else:
              console.print(f"  [dim yellow]? Couldn't verify: {slug}[/dim yellow]")

          console.print(f"  ↳ {added_count} new, {known} already known.")
          logger.info(f"Finished {name}: {added_count} new, {known} known.")

        except Exception as e:
          consecutive_errors += 1
          logger.exception(f"Error searching {name}: {e}")
          console.print(f"[red]  ↳ Error searching {name}: {e}[/red]")

          if consecutive_errors >= 3:
            logger.warning("Circuit breaker triggered: 3 consecutive search failures.")
            console.print("\n[bold red]Stopping early: 3 consecutive searches failed (likely rate-limited).[/bold red]")
            break

        time.sleep(BACKOFF)

      if consecutive_errors >= 3:
        break

  if not found_any:
    logger.info("Discovery run completed. No new slugs found.")
    console.print("\n[yellow]No new company slugs found.[/yellow]")
    return

  raw_config = load_config()
  raw_config.setdefault("companies", {})

  console.print("\n[bold]Discovery Summary:[/bold]")
  for name, slugs in new_slugs.items():
    if slugs:
      console.print(f"[green]+ {name}:[/green] {', '.join(slugs)}")
      existing = set(raw_config["companies"].get(name, []))
      existing.update(slugs)
      raw_config["companies"][name] = sorted(existing)

  if write:
    save_config(raw_config)
    logger.info("Successfully saved new company slugs to config.json.")
    console.print("\n[bold green]Successfully saved to config.json![/bold green]")
  else:
    console.print("\n[yellow]Run with --write to save these slugs to your config.[/yellow]")
