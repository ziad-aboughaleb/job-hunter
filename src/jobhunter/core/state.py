import json
import tempfile
from pathlib import Path
from typing import Any

from jobhunter.models import AIResult, Job

from .paths import get_project_root

DATA_DIR = get_project_root() / "data"
DATA_DIR.mkdir(exist_ok=True)


# helper functions for reading and writing JSON files
def _read_json(filename: str, default: Any) -> Any:
  """Reads JSON data from a file and returns it. If the file does not exist, returns the provided default value."""
  file_path = DATA_DIR / filename

  if not file_path.exists():
    return default

  with open(file_path, encoding="utf-8") as f:
    return json.load(f)


def _atomic_write_json(filename: str, data: Any) -> None:
  """Writes JSON data to a file atomically by first writing to a temporary file and then replacing the target file."""
  target_path = DATA_DIR / filename

  fd, tmp_path = tempfile.mkstemp(dir=DATA_DIR, text=True)
  with open(fd, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)

  Path(tmp_path).replace(target_path)


# Candidate functions
def load_candidates() -> list[Job]:
  """Loads the list of Job objects from a JSON file."""
  raw_data = _read_json("candidates.json", [])
  return [Job(**item) for item in raw_data]


def save_candidates(candidates: list[Job]) -> None:
  """Saves the list of Job objects to a JSON file in an atomic manner."""
  _atomic_write_json("candidates.json", [job.model_dump() for job in candidates])


# Result functions
def load_results() -> list[AIResult]:
  """Loads the list of AIResult objects from a JSON file."""
  raw_data = _read_json("results.json", [])
  return [AIResult(**item) for item in raw_data]


def save_results(results: list[AIResult]) -> None:
  """Saves the list of AIResult objects to a JSON file in an atomic manner."""
  _atomic_write_json("results.json", [result.model_dump() for result in results])


# Seen functions
def load_seen() -> dict[str, str]:
  """Loads the dictionary of already processed Job IDs to prevent duplicate LLM calls."""
  return _read_json("seen.json", {})


def save_seen(new_seen: dict[str, str]) -> None:
  """Saves the updated dictionary of processed Job IDs."""
  _atomic_write_json("seen.json", new_seen)
