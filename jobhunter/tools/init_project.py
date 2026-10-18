"""`init`: create config.json, cv.md, preferences.md and .env from the templates in examples/.

--preset picks a starting set of title and skill words for a kind of role (examples/presets/*.json).
--level adds seniority words to the title lists.
Existing files are never overwritten unless --force is given.
"""
import json
import shutil
import sys
from typing import Dict, List, Optional

from jobhunter.helpers import paths, store
from jobhunter.helpers.config import deep_merge

# Seniority words added to the title lists by `init --level`.
LEVELS: Dict[str, Dict[str, List[str]]] = {
    "junior": {
        "include": ["junior", "entry level", "entry-level", "associate", "trainee", "intern", "internship", "graduate"],
        "exclude": ["director", "vp", "vice president", "head of", "principal", "staff", "lead", "senior", "sr", "sr.",
                    "mid-senior", "mid level", "mid-level", "ii", "iii", "iv", "architect", "manager"],
    },
    "mid": {
        "include": [],
        "exclude": ["director", "vp", "vice president", "head of", "principal", "staff", "lead", "senior", "sr", "sr.",
                    "architect", "manager", "intern", "internship", "trainee", "graduate"],
    },
    "senior": {
        "include": [],
        "exclude": ["intern", "internship", "trainee", "graduate", "junior", "entry level", "entry-level",
                    "director", "vp", "vice president", "head of"],
    },
}


def _unique(items: List[str]) -> List[str]:
    return list(dict.fromkeys(items))


def available_presets() -> List[str]:
    folder = paths.code_root() / "examples" / "presets"
    return sorted(p.stem for p in folder.glob("*.json")) if folder.exists() else []


def build_initial_config(preset: Optional[str], level: Optional[str]) -> dict:
    """examples/config.example.json, plus a role preset and a seniority level if given."""
    examples = paths.code_root() / "examples"
    base = json.loads((examples / "config.example.json").read_text(encoding="utf-8"))
    base.pop("_help", None)
    cfg = base
    preset_filters: dict = {}
    if preset:
        data = json.loads((examples / "presets" / f"{preset}.json").read_text(encoding="utf-8"))
        cfg = deep_merge(base, {"profile": data.get("profile", {})})
        preset_filters = data.get("filters", {})
    filters = cfg["filters"]
    rules = LEVELS.get(level or "", {"include": [], "exclude": []})
    filters["title_include"] = _unique(preset_filters.get("title_include", []) + base["filters"]["title_include"] + rules["include"])
    filters["title_exclude"] = _unique(base["filters"]["title_exclude"] + preset_filters.get("title_exclude", []) + rules["exclude"])
    filters["stack_keywords"] = preset_filters.get("stack_keywords", filters["stack_keywords"])
    filters["min_stack_hits"] = preset_filters.get("min_stack_hits", filters["min_stack_hits"])
    return cfg


def run(preset: Optional[str] = None, level: Optional[str] = None, force: bool = False) -> int:
    root, examples = paths.root(), paths.code_root() / "examples"
    if preset and preset not in available_presets():
        print(f"Unknown preset '{preset}'. Choose from: {', '.join(available_presets())}", file=sys.stderr)
        return 1
    created, skipped = [], []

    def place(name: str, write) -> None:
        target = root / name
        if target.exists() and not force:
            skipped.append(name)
            return
        write(target)
        created.append(name)

    place("config.json", lambda p: store.write_json(p, build_initial_config(preset, level)))
    place("cv.md", lambda p: shutil.copy(examples / "cv.example.md", p))
    place("preferences.md", lambda p: shutil.copy(examples / "preferences.example.md", p))
    place(".env", lambda p: shutil.copy(examples / ".env.example", p))
    paths.data_dir()

    for name in created:
        print(f"created  {name}")
    for name in skipped:
        print(f"kept     {name} (already exists; use --force to overwrite)")
    print("\nNext steps:\n  1. Put your CV in cv.md and fill in preferences.md\n"
          "  2. Put your Telegram bot token, chat id and AI API key in .env\n"
          "  3. python -m jobhunter doctor         (checks everything)\n"
          "  4. python -m jobhunter run --dry-run  (a full test run that sends nothing)\n"
          "Full guide: docs/GETTING_STARTED.md")
    return 0
