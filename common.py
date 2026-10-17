"""Shared helpers for the job-hunter pipeline. Standard library only."""
import json
import os
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent

DEFAULTS = {
    "companies": {"greenhouse": [], "lever": [], "lever_eu": [], "ashby": [], "recruitee": [], "workable": [], "personio": []},
    "boards": {"remotive": True, "remoteok": True, "arbeitnow": False},
    "filters": {
        "title_include": [
            "frontend", "front-end", "front end", "full-stack", "fullstack",
            "full stack", "react", "mern", "web developer", "software engineer",
        ],
        "title_exclude": [
            "intern", "internship", "director", "vp ", "vice president",
            "head of", "principal", "recruiter", "sales", "marketing",
            "designer", "manager",
        ],
        "stack_keywords": [
            "react", "typescript", "javascript", "node", "next.js", "express",
            "mongodb", "redux", "tailwind", "graphql",
        ],
        "min_stack_hits": 2,
        "company_exclude": [],
        "company_priority": [],
        "require_remote": True,
        "location_exclude_terms": [],
        "location_allow_terms": [
            "worldwide", "global", "anywhere", "emea", "europe", "africa",
            "middle east", "apac", "international",
        ],
        "max_age_days": 14,
    },
    "limits": {
        "max_candidates_per_run": 30,
        "description_max_chars": 7000,
        "max_messages": 15,
        "seen_retention_days": 90,
    },
    "score_threshold": 75,
    "llm": {
        "base_url": "http://localhost:11434",
        "model": "qwen2.5:7b",
        "num_ctx": 8192,
        "temperature": 0,
        "keep_alive": "30m",
        "timeout": 600,
        "think": False,
        "provider": "ollama",
        "api_key_env": "LLM_API_KEY",
        "max_output_tokens": 1500,
        "json_mode": "schema",
        "request_delay": 0,
        "extra_body": {},
    },
    "telegram": {"link_preview": False, "notify_on_empty": True},
}


def deep_merge(base, over):
    out = deepcopy(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config():
    path = ROOT / "config.json"
    user = {}
    if path.exists():
        try:
            user = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"config.json is not valid JSON: {exc}")
    return deep_merge(DEFAULTS, user)


def load_env():
    """Read .env (KEY=VALUE lines) without overriding real environment variables."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_json(name, default=None):
    """Return parsed JSON, `default` if the file is missing. Raises JSONDecodeError if invalid."""
    path = ROOT / name
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(name, data):
    path = ROOT / name
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def today_str():
    return datetime.now(timezone.utc).date().isoformat()


def load_seen():
    """seen.json maps job uid -> date it was evaluated (YYYY-MM-DD)."""
    try:
        data = load_json("seen.json", {})
    except json.JSONDecodeError:
        (ROOT / "seen.json").replace(ROOT / "seen.json.bak")
        print("WARNING: seen.json was corrupt; moved to seen.json.bak", file=sys.stderr)
        return {}
    return data if isinstance(data, dict) else {}


def prune_seen(seen, retention_days):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).date().isoformat()
    return {uid: day for uid, day in seen.items() if str(day) >= cutoff}
