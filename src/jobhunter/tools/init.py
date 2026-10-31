import logging
from pathlib import Path

from jobhunter.core.http import fetch_url
from jobhunter.core.logger import console

logger = logging.getLogger(__name__)


def main(dir: Path):
  """Scaffolds a new JobHunter workspace by downloading default templates and docs."""
  logger.info(f"Starting workspace initialization at {dir.absolute()}")

  dir.mkdir(parents=True, exist_ok=True)
  (dir / "config").mkdir(exist_ok=True)
  (dir / "docs").mkdir(exist_ok=True)

  console.print(f"[bold cyan]Initializing JobHunter workspace in {dir.absolute()}...[/bold cyan]")

  base_url = "https://raw.githubusercontent.com/ziad-aboughaleb/job-hunter/main"

  files_to_download = {
    "examples/config.example.json": "config/config.json",
    "examples/cv.example.md": "config/cv.md",
    "examples/preferences.example.md": "config/preferences.md",
    ".env.example": ".env",
    "docs/architecture.md": "docs/architecture.md",
    "docs/configuration.md": "docs/configuration.md",
  }

  created_count = 0
  skipped_count = 0
  failed_count = 0

  console.print("[dim cyan]Downloading templates and documentation...[/dim cyan]")

  for remote_path, local_path in files_to_download.items():
    dest_file = dir / local_path

    if dest_file.exists():
      logger.info(f"Skipped {local_path} (already exists).")
      console.print(f"  [yellow]⚠ Skipped {local_path} (already exists)[/yellow]")
      skipped_count += 1
      continue

    url = f"{base_url}/{remote_path}"
    try:
      logger.info(f"Fetching {url}")
      response = fetch_url(url, follow_redirects=True)
      dest_file.write_text(response.text, encoding="utf-8")

      logger.info(f"Created {local_path}")
      console.print(f"  [green]✔ Created {local_path}[/green]")
      created_count += 1

    except Exception as e:
      logger.exception(f"Error fetching {remote_path}: {e}")
      console.print(f"  [red]✖ Failed to download {remote_path}: {e}[/red]")
      failed_count += 1

  logger.info(f"Initialization finished. Created: {created_count} | Skipped: {skipped_count} | Failed: {failed_count}")

  console.print("\n[bold]Initialization Summary[/bold]")
  console.print("───────────────────────────────────────")
  console.print(f"Files created : [bold green]{created_count}[/bold green]")
  console.print(f"Files skipped : [yellow]{skipped_count}[/yellow]")
  console.print(f"Files failed  : [red]{failed_count}[/red]")
  console.print("───────────────────────────────────────\n")

  if created_count > 0 or skipped_count > 0:
    console.print("[bold green]✔ Workspace is ready![/bold green]")
    console.print(f"1. Open [bold cyan]{dir / '.env'}[/bold cyan] and add your API keys.")
    console.print(f"2. Customize your cv, preferences and config in [bold cyan]{dir / 'config/'}[/bold cyan].")
    console.print("3. Run [bold cyan]jobhunter run[/bold cyan] to start the pipeline.\n")
