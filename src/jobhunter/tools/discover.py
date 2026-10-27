import time
from urllib.parse import urlparse

from ddgs import DDGS
from rich.console import Console

from jobhunter.core.settings import settings
from jobhunter.core.state import load_config, save_config
from jobhunter.sources import SOURCES
from jobhunter.sources.base import SlugStatus

console = Console()

# Blacklist of common paths that are NOT company slugs
INVALID_SLUGS = {
  "blog",
  "blogs",
  "guides",
  "docs",
  "html",
  "role",
  "i",
  "p",
  "j",
  "embed",
  "career-advice",
  "careers",
  "jobs",
  "about",
  "support",
  "www",
  "pricing",
  "login",
  "signup",
  "resources",
  "contact",
  "legal",
  "privacy",
  "terms",
  "hire",
  "freelance-jobs",
  "what-is",
  "software-engineer-full-stack",
  "front-end-vs-back-end-vs-full-stack-2",
  "gfg-academy",
}


def extract_slug(url: str, source_name: str) -> str | None:
  source = SOURCES.get(source_name)
  if not url or not source or not getattr(source, "domains", None):
    return None

  host = (urlparse(url).hostname or "").lower()
  for domain in source.domains:
    if host == domain or host.endswith(f".{domain}"):
      if getattr(source, "is_subdomain", False):
        prefix = host[: -len(domain)].rstrip(".")
        slug = prefix.split(".")[0] if prefix else None
      else:
        parts = [p for p in urlparse(url).path.split("/") if p]
        slug = parts[0].lower() if parts else None
      return slug if slug and slug not in INVALID_SLUGS else None
  return None


def main(write: bool = False, source_name: str | None = None, titles_override: str | None = None):
  """Discovers new company slugs by searching for target titles on configured sources."""
  if source_name:
    if source_name not in SOURCES:
      console.print(f"[red]Error: Source '{source_name}' is not configured in your scrapers.[/red]")
      return

    source = SOURCES[source_name]
    if getattr(source, "is_aggregator", False):
      console.print(f"[yellow]Notice: '{source_name}' is an aggregator. Discovery is only for finding ATS company slugs.[/yellow]")
      return

  if titles_override:
    titles = [t.strip() for t in titles_override.split(",")]
  else:
    titles = settings.filters.title_include
    if not titles:
      console.print("[red]No target titles found in config.json filters.title_include.[/red]")
      return

  titles_query = " OR ".join(f'"{t}"' for t in titles[:6])

  new_slugs = {name: set() for name in settings.companies}
  found_any = False

  with DDGS() as ddgs:
    for name, source in SOURCES.items():
      if source_name and name != source_name:
        continue

      if getattr(source, "is_aggregator", False) or not getattr(source, "domains", None):
        continue

      for domain in source.domains:
        query = f"site:{domain} {titles_query}"

        console.print(f"\n[cyan]Searching [bold]{name}[/bold][/cyan] ([dim]{query}[/dim])...")

        results = []

        try:
          for attempt in range(3):
            try:
              results = list(ddgs.text(query, max_results=30))
              break
            except Exception:
              if attempt == 2:
                raise
              time.sleep(4 * (attempt + 1))

          added_count = 0
          known = 0

          for result in results:
            url = result.get("href", "")
            slug = extract_slug(url, name)

            if not slug:
              if url and any((urlparse(url).hostname or "").endswith(d) for d in source.domains):
                console.print(f"  [dim yellow]⚠ Ignored URL: {url}[/dim yellow]")
              continue

            existing = settings.companies.get(name, [])
            if slug in existing and slug in new_slugs.get(name, set()):
              known += 1
              continue

            status = source.validate_slug(slug)
            if status is SlugStatus.VALID:
              new_slugs.setdefault(name, set()).add(slug)
              added_count += 1
              found_any = True
            elif status is SlugStatus.INVALID:
              console.print(f"  [dim red]✖ Not a real board: {slug}[/dim red]")
            else:
              console.print(f"  [dim yellow]? Couldn't verify: {slug}[/dim yellow]")

          console.print(f"  ↳ {added_count} new, {known} already known.")

        except Exception as e:
          console.print(f"[red]  ↳ Error searching {name}: {e}[/red]")

  if not found_any:
    console.print("\n[yellow]No new company slugs found.[/yellow]")
    return

  raw_config = load_config()

  if "companies" not in raw_config:
    raw_config["companies"] = {}

  console.print("\n[bold]Discovery Summary:[/bold]")
  for name, slugs in new_slugs.items():
    if slugs:
      console.print(f"[green]+ {name}:[/green] {', '.join(slugs)}")

      existing = set(raw_config["companies"].get(name, []))
      existing.update(slugs)
      raw_config["companies"][name] = sorted(existing)

  if write:
    save_config(raw_config)
    console.print("\n[bold green]Successfully saved to config.json![/bold green]")
  else:
    console.print("\n[yellow]Run with --write to save these slugs to your config.[/yellow]")
