import importlib
import pkgutil
from pathlib import Path

from jobhunter.models import Job

SOURCES = {}

current_dir = str(Path(__file__).parent)

for _, module_name, _ in pkgutil.iter_modules([current_dir]):
  if module_name == "base":
    continue

  module = importlib.import_module(f".{module_name}", package=__name__)

  if hasattr(module, "Source"):
    source_instance = module.Source()
    if getattr(source_instance, "enabled", True):
      SOURCES[source_instance.name] = source_instance


def execute_scraper(source, slug: str = "") -> list[Job]:
  """Executes the scraper for a given source and slug."""
  return source.fetch(slug=slug) or []


__all__ = ["SOURCES", "execute_scraper"]
