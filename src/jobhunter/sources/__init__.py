import importlib
import pkgutil
from pathlib import Path

import httpx

from jobhunter.core.logger import get_logger
from jobhunter.models import Job

logger = get_logger(__name__)

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
  if not source.enabled:
    return []

  if not source.is_aggregator and not slug:
    logger.warning(f"[{source.name}] Skipping execution: Non-aggregator sources require a slug.")
    return []

  try:
    return source.fetch(slug=slug) or []
  except httpx.HTTPStatusError as e:
    logger.error(f"[{source.name}] HTTP {e.response.status_code} error for slug '{slug}': {e}")
    return []
  except ValueError as e:
    logger.error(f"[{source.name}] Validation error for slug '{slug}': {e}")
    return []
  except Exception as e:
    logger.exception(f"[{source.name}] Unexpected error executing scraper for slug '{slug}': {e}")
    return []


__all__ = ["SOURCES", "execute_scraper"]
