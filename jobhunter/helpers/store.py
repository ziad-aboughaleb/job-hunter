"""Reading and writing the files the tool keeps between stages and between runs.

The three stages never call each other directly. They talk through files in data/:

    fetch    -> data/candidates.json, data/run_status.json
    evaluate -> data/results.json
    send     -> data/seen.json   (what has already been dealt with)
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

from jobhunter.helpers import paths


def read_json(path: Path, default: Any = None) -> Any:
    """Parsed JSON, or `default` if the file does not exist. Invalid JSON raises json.JSONDecodeError."""
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    """Write JSON atomically (temp file, then rename) so a crash never leaves half a file."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def read_data(name: str, default: Any = None) -> Any:
    return read_json(paths.data_dir() / name, default)


def write_data(name: str, data: Any) -> None:
    write_json(paths.data_dir() / name, data)


def delete_data(*names: str) -> None:
    for name in names:
        (paths.data_dir() / name).unlink(missing_ok=True)


def read_text(name: str) -> str:
    """Text of a file in the project folder (cv.md, preferences.md). Empty string if missing."""
    path = paths.root() / name
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


# --------------------------------------------------------------------------- #
# seen.json: which jobs we are finished with
# --------------------------------------------------------------------------- #
SEEN_FILE = "seen.json"


def load_seen() -> Dict[str, str]:
    """Map of job uid -> date (YYYY-MM-DD) it was dealt with."""
    path = paths.data_dir() / SEEN_FILE
    legacy = paths.root() / SEEN_FILE  # older versions kept seen.json next to config.json
    if not path.exists() and legacy.exists():
        path = legacy
    try:
        data = read_json(path, {})
    except json.JSONDecodeError:
        path.replace(path.with_name(path.name + ".bak"))
        print(f"WARNING: {path.name} was corrupt; moved to {path.name}.bak and started fresh.", file=sys.stderr)
        return {}
    return data if isinstance(data, dict) else {}


def save_seen(seen: Dict[str, str], retention_days: int) -> None:
    """Save, forgetting entries older than `retention_days` so the file stays small."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).date().isoformat()
    write_data(SEEN_FILE, {uid: day for uid, day in seen.items() if str(day) >= cutoff})


def today() -> str:
    return datetime.now(timezone.utc).date().isoformat()
