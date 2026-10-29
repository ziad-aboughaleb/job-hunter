import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from filelock import FileLock

from jobhunter.core.logger import get_logger

logger = get_logger(__name__)


def get_project_root() -> Path:
  """Returns the root directory of the project by searching for 'pyproject.toml'."""
  current_dir = Path(__file__).resolve().parent

  for directory in [current_dir, *current_dir.parents]:
    if (directory / "pyproject.toml").exists():
      return directory

  return Path.cwd()


ROOT_PATH = get_project_root()
DATA_PATH = ROOT_PATH / "data"
CONFIG_PATH = ROOT_PATH / "config"


def _resolve_path(path_in: str | Path) -> Path:
  """
  Safely resolves a path against the project root.
  If path_in is absolute (e.g. DATA_PATH / 'file.json'), it returns it as-is.
  If path_in is relative (e.g. 'data/file.json'), it prepends ROOT_PATH.
  """
  return ROOT_PATH / path_in


def _json_default(obj: Any) -> Any:
  """Fallback handler for non-standard JSON types like Pydantic models."""
  if hasattr(obj, "model_dump"):
    return obj.model_dump(mode="json")
  return str(obj)


def write(path_from_root: str | Path, data: Any, timeout: int = 10):
  """Atomically writes data to disk, using a lockfile to prevent multiple processes from writing at the exact same time."""
  path = _resolve_path(path_from_root)

  directory = path.parent
  try:
    directory.mkdir(parents=True, exist_ok=True)
  except Exception as e:
    logger.error(f"Failed to create directory {directory}: {e}")
    raise

  # Universal Data Conversion
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

  # Acquire the Lock
  lock_path = path.with_suffix(path.suffix + ".lock")

  try:
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

      except Exception as e:
        logger.error(f"Failed to write atomically to {path}: {e}")
        if os.path.exists(temp_path):
          os.remove(temp_path)
        raise

  except Exception as e:
    logger.error(f"Write operation failed for {path} (Lock or IO Error): {e}")
    raise
  finally:
    with contextlib.suppress(OSError):
      lock_path.unlink()


def read[T: (dict, list, str)](
  path_from_root: str | Path,
  expected_type: type[T] = str,  # type: ignore[assignment]
) -> T:
  """Reads the file and validates it to the requested type. Returns an empty default ({}, [], or "") if the file is missing."""
  path = _resolve_path(path_from_root)

  try:
    text = path.read_text(encoding="utf-8")
  except FileNotFoundError:
    return expected_type()
  except Exception as e:
    logger.error(f"Failed to read file {path}: {e}")
    raise

  if expected_type in (dict, list):
    try:
      data = json.loads(text)
    except json.JSONDecodeError as e:
      logger.error(f"JSON corruption detected in {path}: {e}")
      raise

    if not isinstance(data, expected_type):
      logger.error(f"Type mismatch in {path}: Expected {expected_type.__name__}, got {type(data).__name__}")
      raise TypeError(f"Expected {expected_type.__name__}, got {type(data).__name__}")

    return data  # type: ignore[return-value]

  return text  # type: ignore[return-value]


def delete(path_from_root: str | Path):
  """Unlinks the file safely without throwing an error if it doesn't exist."""
  path = _resolve_path(path_from_root)

  try:
    path.unlink()
  except FileNotFoundError:
    pass
  except Exception as e:
    logger.error(f"Failed to delete file {path}: {e}")
    raise
