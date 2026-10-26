import time
from urllib.parse import urlparse

from ddgs import DDGS
from rich.console import Console

from jobhunter.core.settings import settings
from jobhunter.core.state import load_config, save_config
from jobhunter.sources import SOURCES

console = Console()


def extract_slug(url: str, source_name: str) -> str | None:
  """Extracts a company slug from a given URL based on the source's URL structure."""
  try:
    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.split("/") if p]

    source = SOURCES.get(source_name)
    is_subdomain = getattr(source, "is_subdomain", False)

    if is_subdomain:
      host_parts = parsed.netloc.split(".")
      if len(host_parts) >= 3:
        slug = host_parts[0]
        if slug not in ["www", "jobs", "careers"]:
          return slug
      return None

    if path_parts:
      slug = path_parts[0]
      if slug.lower() not in ["jobs", "careers", "p", "j", "embed"]:
        return slug

  except Exception:
    pass

  return None


def main(write: bool = False, source_name: str | None = None, titles_override: str | None = None):
  """Discovers new company slugs by searching for target titles on configured sources."""
  if titles_override:
    titles = titles_override.split(",")
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

      domain = source.domains[0]
      query = f"site:{domain} {titles_query}"

      console.print(f"\n[cyan]Searching [bold]{name}[/bold][/cyan] ([dim]{query}[/dim])...")

      try:
        results = ddgs.text(query, max_results=30)

        added_count = 0

        for result in results:
          url = result.get("href", "")
          slug = extract_slug(url, name)

          if slug:
            existing = settings.companies.get(name, [])
            if slug not in existing and slug not in new_slugs.get(name, set()):
              new_slugs.setdefault(name, set()).add(slug)
              added_count += 1
              found_any = True
          else:
            console.print(f"\n[dim yellow]⚠ Unrecognized URL format: {url}[/dim yellow]")

        console.print(f" ↳ Found {added_count} new slugs.")

      except Exception as e:
        console.print(f"[red] ↳ Error searching {name}: {e}[/red]")

      time.sleep(2)

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
