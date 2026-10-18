"""Optional helper: find company names to put in config.json -> companies.

The searches are built from YOUR config (filters.title_include), so discovery looks for the same kinds of jobs
the pipeline filters for. It needs the optional `ddgs` package:   python -m pip install ddgs
Run it by hand now and then; it is not part of the daily run (search engines rate-limit).
"""
import re
import sys
import time
from typing import Dict, List, Optional, Tuple

from jobhunter.helpers import paths, store
from jobhunter.helpers.config import load_config

SITES = {
    "greenhouse": ["job-boards.greenhouse.io", "boards.greenhouse.io"],
    "lever": ["jobs.lever.co"],
    "ashby": ["jobs.ashbyhq.com"],
    "workable": ["apply.workable.com"],
    "recruitee": ["recruitee.com"],
    "personio": ["jobs.personio.de", "jobs.personio.com"],
}

# How to pull the company name out of a result URL.
URL_PATTERNS = {
    "greenhouse": re.compile(r"greenhouse\.io/(?:embed/job_app\?for=)?([A-Za-z0-9_-]+)"),
    "lever": re.compile(r"jobs\.lever\.co/([A-Za-z0-9_.-]+)"),
    "ashby": re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_.%-]+)"),
    "workable": re.compile(r"apply\.workable\.com/([A-Za-z0-9_-]+)"),
    "recruitee": re.compile(r"//([A-Za-z0-9-]+)\.recruitee\.com"),
    "personio": re.compile(r"//([A-Za-z0-9-]+)\.jobs\.personio\.(?:de|com)"),
}
NOT_COMPANIES = {"embed", "jobs", "job_app", "www", "api", "j", "o", "careers", "app", "apply"}

# Titles too generic to search on their own: they would return every kind of job.
GENERIC_TITLES = {"engineer", "developer", "software engineer", "software developer", "junior", "entry level",
                  "entry-level", "js", "intern", "internship", "trainee", "graduate", "associate"}


def topics_from_config(cfg: dict, include_generic: bool = False, max_topics: int = 6) -> List[str]:
    """Search topics taken from filters.title_include, in order.

    Spelling variants (front-end / frontend / front end) count once, and generic words are skipped.
    """
    seen, topics = set(), []
    for term in cfg["filters"]["title_include"]:
        term = term.strip()
        key = re.sub(r"[^a-z0-9]", "", term.lower())
        if not key or key in seen or (not include_generic and term.lower() in GENERIC_TITLES):
            continue
        seen.add(key)
        topics.append(term)
    return topics[:max_topics]


def company_from_url(platform: str, url: str) -> Optional[str]:
    match = URL_PATTERNS[platform].search(url or "")
    if match and match.group(1).lower() not in NOT_COMPANIES:
        return match.group(1)
    return None


def _search(ddgs, query: str, max_results: int, recent: bool) -> Tuple[list, Optional[str]]:
    """(results, error). An empty search is not an error. A rate limit gets one retry after a pause."""
    options = {"timelimit": "m"} if recent else {}
    for attempt in range(2):
        try:
            return list(ddgs.text(query, max_results=max_results, **options)), None
        except Exception as exc:
            message = str(exc).lower()
            if "no results" in message:  # the search library raises this when nothing matched
                return [], None
            if attempt == 0 and any(x in message for x in ("ratelimit", "rate limit", "202", "429")):
                time.sleep(15)
                continue
            return [], str(exc)
    return [], "rate limited"


def run(write: bool = False, only: str = "", max_topics: int = 6, include_generic: bool = False,
        results_per_search: int = 30, delay: float = 2.0, recent: bool = False) -> int:
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS  # the old package name
        except ImportError:
            print("The search package is missing. Install it with:  python -m pip install ddgs", file=sys.stderr)
            return 1

    cfg = load_config()
    platforms = [p.strip() for p in only.split(",") if p.strip()] or list(SITES)
    unknown = [p for p in platforms if p not in SITES]
    if unknown:
        print(f"Unknown platform(s): {unknown}. Choose from {list(SITES)}", file=sys.stderr)
        return 1
    topics = topics_from_config(cfg, include_generic, max_topics)
    if not topics:
        print("No usable topics: filters.title_include is empty or only has generic words (use --include-generic).",
              file=sys.stderr)
        return 1

    suffix = " remote" if cfg["filters"]["require_remote"] else ""
    queries = [(p, f'site:{host} "{topic}"{suffix}') for p in platforms for host in SITES[p] for topic in topics]
    print(f"Topics from your config: {topics}")
    print(f"{len(queries)} searches, roughly {len(queries) * (delay + 3) / 60:.0f} minute(s).\n")

    known = {p: {name.lower() for name in cfg["companies"].get(p, [])} for p in SITES}
    found: Dict[str, Dict[str, str]] = {p: {} for p in SITES}  # lowercase name -> first spelling, so Tempo/tempo count once
    ddgs, errors_in_a_row = DDGS(), 0

    for i, (platform, query) in enumerate(queries, start=1):
        results, error = _search(ddgs, query, results_per_search, recent)
        if error:
            errors_in_a_row += 1
            print(f"[{i}/{len(queries)}] {query}\n    search failed: {error}")
            if errors_in_a_row >= 3:
                print("\nStopping: 3 searches in a row failed with a real error (usually rate limiting). "
                      "Wait a while and run again; what was found so far is shown below.")
                break
        else:
            errors_in_a_row = 0
            before = len(found[platform])
            for result in results:
                name = company_from_url(platform, result.get("href", ""))
                if name:
                    found[platform].setdefault(name.lower(), name)
            print(f"[{i}/{len(queries)}] {query}  ->  {len(results)} results, {len(found[platform]) - before} new")
        time.sleep(delay)

    new = {p: sorted(name for low, name in found[p].items() if low not in known[p]) for p in platforms}
    print("\nNew company names:")
    for platform, names in new.items():
        print(f"  {platform}: {names or '-'}")

    if write and any(new.values()):
        path = paths.root() / "config.json"
        data = store.read_json(path, {})
        for platform, names in new.items():
            data.setdefault("companies", {}).setdefault(platform, []).extend(names)
        store.write_json(path, data)
        print("\nconfig.json updated.")
    elif any(new.values()):
        print("\nRe-run with --write to add them to config.json.")
    return 0
