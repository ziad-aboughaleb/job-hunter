"""Loading config.json, filling in defaults, and warning about mistakes.

Every setting has a default (DEFAULTS below), so config.json only needs the settings you change.
Settings whose name starts with an underscore (like "_help") are ignored: use them for notes.
"""
import json
import os
import sys
from copy import deepcopy
from typing import Any, Dict, List

from jobhunter.helpers import paths

DEFAULT_WEIGHTS = [
    {"name": "Core skills overlap", "weight": 40, "what": "required technologies and skills that the CV demonstrates"},
    {"name": "Experience and seniority fit", "weight": 20, "what": "years and level compared with the CV"},
    {"name": "Role type and location fit", "weight": 20, "what": "title fit, and a work arrangement and location that suit the candidate"},
    {"name": "Nice-to-haves", "weight": 20, "what": "secondary tools, methodologies and soft skills"},
]

DEFAULTS: Dict[str, Any] = {
    # What kind of job you are hunting. Used inside the scoring prompt (the "role" hard gate).
    "profile": {"target_roles": "software engineering work that fits the candidate's CV and preferences"},

    # Aggregator sites that list many companies at once. Each value is true/false, or an object with options.
    "boards": {
        "remotive": {"enabled": True, "category": "software-dev"},
        "remoteok": {"enabled": True},
        "arbeitnow": {"enabled": False},
    },

    # Optional: specific companies to watch. The value is the company's name in its job-board URL.
    "companies": {"greenhouse": [], "lever": [], "lever_eu": [], "ashby": [],
                  "recruitee": [], "workable": [], "personio": []},

    # Rules applied to every job BEFORE the AI sees it. See docs/CONFIG.md for the order they run in.
    "filters": {
        "title_include": ["engineer", "developer"],  # a job's title must contain at least one of these
        "title_exclude": [],                          # ...and none of these (whole words)
        "stack_keywords": [],                         # skills to look for in the title + description
        "min_stack_hits": 0,                          # how many distinct stack_keywords a job needs
        "company_exclude": [],
        "company_priority": [],
        "require_remote": True,
        "location_exclude_terms": [],
        "location_allow_terms": [],
        "location_require_terms": [],
        "max_age_days": 14,
    },

    "limits": {
        "max_candidates_per_run": 30,   # most jobs sent to the AI per run
        "description_max_chars": 7000,  # longest description kept per job
        "max_messages": 15,             # most Telegram job cards per run
        "seen_retention_days": 90,      # how long finished jobs are remembered
        "fetch_workers": 8,             # sources fetched in parallel
    },

    "score_threshold": 75,              # score needed for a Telegram message
    "scoring_weights": DEFAULT_WEIGHTS,  # how the AI should weigh things; weights should add up to 100

    "llm": {
        "provider": "openai",           # "openai" = any OpenAI-compatible API (Gemini, OpenAI, ...); "ollama" = local
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-3.5-flash-lite",
        "api_key_env": "LLM_API_KEY",   # name of the environment variable holding the key
        "temperature": 0,
        "timeout": 600,
        "num_ctx": 32768,               # context size; also used to size the job text
        "max_output_tokens": 2500,
        "json_mode": "schema",          # "schema" (strict) or "object" (plain JSON mode)
        "request_delay": 0,             # seconds to wait between jobs (free tiers need ~5)
        "extra_body": {},               # extra fields merged into every API request
        "think": False,                 # Ollama only
        "keep_alive": "30m",            # Ollama only
    },

    "telegram": {"link_preview": False, "notify_on_empty": True},
}

# Settings whose contents are free-form, so unknown names inside them are not typos.
FREE_FORM = {"companies", "boards", "llm.extra_body", "scoring_weights"}


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Copy of `base` with `override` laid on top. Dicts merge key by key; everything else is replaced."""
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def board_options(value: Any) -> Dict[str, Any]:
    """A board can be written as true/false or as an object with options. Return the object form."""
    if isinstance(value, dict):
        options = dict(value)
        options.setdefault("enabled", True)
        return options
    return {"enabled": bool(value)}


def _unknown_keys(user: Dict[str, Any], defaults: Dict[str, Any], path: str = "") -> List[str]:
    """Names in config.json that the tool does not know, which are usually typos."""
    problems = []
    for key, value in user.items():
        if key.startswith("_"):
            continue
        name = f"{path}{key}"
        if key not in defaults:
            problems.append(f"unknown setting '{name}' (typo? it will be ignored)")
        elif name not in FREE_FORM and isinstance(value, dict) and isinstance(defaults[key], dict):
            problems.extend(_unknown_keys(value, defaults[key], name + "."))
    return problems


def validate(cfg: Dict[str, Any]) -> List[str]:
    """Human-readable warnings about values that are likely mistakes."""
    problems = []
    if not 1 <= int(cfg["score_threshold"]) <= 100:
        problems.append("score_threshold should be between 1 and 100")
    total = sum(int(w.get("weight", 0)) for w in cfg["scoring_weights"])
    if total != 100:
        problems.append(f"scoring_weights add up to {total}, not 100")
    for key in ("title_include", "title_exclude", "stack_keywords", "location_exclude_terms",
                "location_allow_terms", "location_require_terms", "company_exclude", "company_priority"):
        if not all(isinstance(item, str) for item in cfg["filters"][key]):
            problems.append(f"filters.{key} must be a list of text values")
    if cfg["llm"]["provider"] not in ("openai", "ollama"):
        problems.append("llm.provider must be 'openai' or 'ollama'")
    if cfg["filters"]["min_stack_hits"] > 0 and not cfg["filters"]["stack_keywords"]:
        problems.append("filters.min_stack_hits is set but stack_keywords is empty: no job can pass")
    return problems


def load_env() -> None:
    """Read KEY=VALUE lines from .env into the environment.

    A variable that is already set to a non-empty value wins over .env. Empty values count as "not set",
    on either side: a blank line in .env is skipped, and an empty variable (an unset CI secret, say) is filled in.
    """
    path = paths.root() / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if value and not os.environ.get(key):
            os.environ[key] = value


def load_config(quiet: bool = False) -> Dict[str, Any]:
    """config.json merged over the defaults. Prints warnings about likely mistakes unless quiet."""
    path = paths.root() / "config.json"
    user: Dict[str, Any] = {}
    if path.exists():
        try:
            user = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"config.json is not valid JSON: {exc}")
    cfg = deep_merge(DEFAULTS, user)
    if not quiet:
        for warning in _unknown_keys(user, DEFAULTS) + validate(cfg):
            print(f"WARNING (config.json): {warning}", file=sys.stderr)
    return cfg
