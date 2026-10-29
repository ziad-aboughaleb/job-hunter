import contextlib
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from filelock import FileLock


def get_project_root() -> Path:
  """Returns the root directory of the project by searching for 'pyproject.toml'."""
  current_dir = Path(__file__).resolve().parent

  for directory in [current_dir, *current_dir.parents]:
    if (directory / "pyproject.toml").exists():
      return directory

  return Path.cwd()


ROOT_PATH = get_project_root()
LOCKS_PATH = ROOT_PATH / ".locks"
DATA_PATH = ROOT_PATH / "data"
CONFIG_PATH = ROOT_PATH / "config"


def _resolve_path(path_in: str | Path) -> Path:
  """
  Safely resolves a path against the project root.
  If path_in is absolute, it returns it as-is.
  If path_in is relative, it prepends ROOT_PATH.
  """
  return ROOT_PATH / path_in


def _json_default(obj: Any) -> Any:
  """Fallback handler for non-standard JSON types like Pydantic models."""
  if hasattr(obj, "model_dump"):
    return obj.model_dump(mode="json")
  return str(obj)


def write(path_from_root: str | Path, data: Any, timeout: int = 10):
  """Atomically writes data to disk using a persistent lockfile for process safety."""
  path = _resolve_path(path_from_root)

  directory = path.parent
  directory.mkdir(parents=True, exist_ok=True)
  LOCKS_PATH.mkdir(exist_ok=True)

  if isinstance(data, bytes):
    raw_bytes = data
  elif isinstance(data, str):
    raw_bytes = data.encode("utf-8")
  elif isinstance(data, (dict, list)):
    raw_bytes = json.dumps(data, indent=4, default=_json_default).encode("utf-8")
  elif hasattr(data, "model_dump"):
    raw_bytes = json.dumps(data.model_dump(mode="json"), indent=4).encode("utf-8")
  else:
    raw_bytes = str(data).encode("utf-8")

  path_hash = hashlib.md5(str(path.resolve()).encode()).hexdigest()
  lock_path = LOCKS_PATH / f"{path.name}_{path_hash}.lock"

  with FileLock(str(lock_path), timeout=timeout):
    fd, temp_path = tempfile.mkstemp(dir=directory, prefix=".tmp_")

    try:
      with os.fdopen(fd, "wb") as f:
        f.write(raw_bytes)
        f.flush()
        if hasattr(os, "fdatasync"):
          os.fdatasync(f.fileno())
        else:
          os.fsync(f.fileno())

      os.replace(temp_path, path)

    except Exception:
      with contextlib.suppress(OSError):
        if os.path.exists(temp_path):
          os.remove(temp_path)
      raise


def read[T: (dict, list, str)](
  path_from_root: str | Path,
  expected_type: type[T] = str,
) -> T:
  """Reads and parses a file. Returns a default empty instance ({}, [], "") if missing."""
  path = _resolve_path(path_from_root)

  try:
    text = path.read_text(encoding="utf-8")
  except FileNotFoundError:
    return expected_type()

  if expected_type in (dict, list):
    data = json.loads(text)

    if not isinstance(data, expected_type):
      raise TypeError(f"Type mismatch in {path}: Expected {expected_type.__name__}, got {type(data).__name__}")

    return data

  return text  # type: ignore


def delete(path_from_root: str | Path):
  """Safely unlinks a file if it exists."""
  _resolve_path(path_from_root).unlink(missing_ok=True)
