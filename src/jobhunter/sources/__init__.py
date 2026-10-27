import importlib
import pkgutil
from pathlib import Path

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


__all__ = ["SOURCES"]
