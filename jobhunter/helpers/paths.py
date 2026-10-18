"""Where files live.

Everything is relative to the *project folder*: the current directory, or the folder named in the
JOBHUNTER_HOME environment variable. Run the tool from the folder that holds config.json.

    <project folder>/
        config.json, cv.md, preferences.md, .env      <- your files (you edit these)
        data/                                         <- files the tool writes (candidates.json, seen.json, ...)
"""
import os
from pathlib import Path


def root() -> Path:
    """The project folder."""
    return Path(os.environ.get("JOBHUNTER_HOME") or Path.cwd()).resolve()


def data_dir() -> Path:
    """Folder for files the tool generates. Created on demand."""
    path = root() / "data"
    path.mkdir(exist_ok=True)
    return path


def code_root() -> Path:
    """The repository folder: the one that contains the jobhunter package, examples/ and docs/."""
    return Path(__file__).resolve().parent.parent.parent
