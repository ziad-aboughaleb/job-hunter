#!/usr/bin/env python3
"""
Optional helper: find company board names (slugs) to put in config.json.

The search topics come from YOUR config.json (filters.title_include), so discovery looks for the
same kinds of jobs the pipeline filters for. Run it by hand now and then, NOT in the daily cron.

    python -m pip install ddgs
    python3 discover_companies.py                   # print suggestions
    python3 discover_companies.py --write           # also add them to config.json
    python3 discover_companies.py --only workable,recruitee --max-topics 4
"""
import argparse
import re
import sys
import time

from common import ROOT, load_config, save_json

try:
    from ddgs import DDGS
except ImportError:
    try:
        from duckduckgo_search import DDGS  # old package name
    except ImportError:
        sys.exit("The search package is missing. Install it with:  python -m pip install ddgs")

import json

SITES = {
    "greenhouse": ["job-boards.greenhouse.io", "boards.greenhouse.io"],
    "lever": ["jobs.lever.co"],
    "ashby": ["jobs.ashbyhq.com"],
    "workable": ["apply.workable.com"],
    "recruitee": ["recruitee.com"],
    "personio": ["jobs.personio.de", "jobs.personio.com"],
}
PATTERNS = {
    "greenhouse": re.compile(r"greenhouse\.io/(?:embed/job_app\?for=)?([A-Za-z0-9_-]+)"),
    "lever": re.compile(r"jobs\.lever\.co/([A-Za-z0-9_.-]+)"),
    "ashby": re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_.%-]+)"),
    "workable": re.compile(r"apply\.workable\.com/([A-Za-z0-9_-]+)"),
    "recruitee": re.compile(r"//([A-Za-z0-9-]+)\.recruitee\.com"),
    "personio": re.compile(r"//([A-Za-z0-9-]+)\.jobs\.personio\.(?:de|com)"),
}
IGNORE = {"embed", "jobs", "job_app", "www", "api", "j", "o", "careers", "app", "apply"}

# Titles too generic to search on their own (they would return every kind of job).
GENERIC = {"engineer", "developer", "software engineer", "software developer", "junior",
           "entry level", "entry-level", "js", "intern", "internship", "trainee", "graduate", "associate"}


def topics_from_config(cfg, include_generic, max_topics):
    """Take filters.title_include in order, drop spelling variants (front-end/frontend/front end) and generic words."""
    seen, topics = set(), []
    for term in cfg["filters"]["title_include"]:
        term = term.strip()
        key = re.sub(r"[^a-z0-9]", "", term.lower())
        if not key or key in seen:
            continue
        if not include_generic and term.lower() in GENERIC:
            continue
        seen.add(key)
        topics.append(term)
    return topics[:max_topics]


def run_search(ddgs, query, max_results, recent):
    """Returns (results, error). An empty search is NOT an error. Rate limits get one retry after a pause."""
    kwargs = {"timelimit": "m"} if recent else {}
    for attempt in range(2):
        try:
            return list(ddgs.text(query, max_results=max_results, **kwargs)), None
        except Exception as exc:
            message = str(exc).lower()
            if "no results" in message:  # ddgs raises this when a search finds nothing
                return [], None
            if attempt == 0 and any(x in message for x in ("ratelimit", "rate limit", "202", "429")):
                time.sleep(15)
                continue
            return [], str(exc)
    return [], "rate limited"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="add new slugs to config.json")
    ap.add_argument("--only", default="", help="comma-separated platforms, e.g. workable,recruitee")
    ap.add_argument("--max-topics", type=int, default=6, help="how many config titles to search for (default 6)")
    ap.add_argument("--include-generic", action="store_true", help="also search generic titles like 'engineer'")
    ap.add_argument("--results", type=int, default=30, help="results per search (default 30)")
    ap.add_argument("--recent", action="store_true",
                    help="only postings from the last month (fewer results; the default has no time limit, "
                         "which is fine because a company name does not expire)")
    ap.add_argument("--delay", type=float, default=2.0, help="seconds between searches (default 2)")
    args = ap.parse_args()

    cfg = load_config()
    platforms = [p.strip() for p in args.only.split(",") if p.strip()] or list(SITES)
    unknown = [p for p in platforms if p not in SITES]
    if unknown:
        sys.exit(f"Unknown platform(s): {unknown}. Choose from {list(SITES)}")

    topics = topics_from_config(cfg, args.include_generic, args.max_topics)
    if not topics:
        sys.exit("No usable topics: filters.title_include is empty or only has generic words "
                 "(use --include-generic).")
    suffix = " remote" if cfg["filters"]["require_remote"] else ""
    queries = [(p, f'site:{host} "{topic}"{suffix}') for p in platforms for host in SITES[p] for topic in topics]

    print(f"Topics from your config: {topics}")
    print(f"{len(queries)} searches, roughly {len(queries) * (args.delay + 3) / 60:.0f} minute(s).\n")

    known = {p: {s.lower() for s in cfg["companies"].get(p, [])} for p in SITES}
    found = {p: set() for p in SITES}
    ddgs = DDGS()
    errors_in_a_row = 0

    for i, (platform, query) in enumerate(queries, start=1):
        results, error = run_search(ddgs, query, args.results, args.recent)
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
            for r in results:
                m = PATTERNS[platform].search(r.get("href", ""))
                if m and m.group(1).lower() not in IGNORE:
                    found[platform].add(m.group(1))
            print(f"[{i}/{len(queries)}] {query}  ->  {len(results)} results, {len(found[platform]) - before} new")
        time.sleep(args.delay)

    new = {p: sorted(s for s in found[p] if s.lower() not in known[p]) for p in platforms}
    print("\nNew company names:")
    for p, slugs in new.items():
        print(f"  {p}: {slugs or '-'}")

    if args.write and any(new.values()):
        path = ROOT / "config.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for p, slugs in new.items():
            data.setdefault("companies", {}).setdefault(p, []).extend(slugs)
        save_json("config.json", data)
        print("\nconfig.json updated.")
    elif any(new.values()):
        print("\nRe-run with --write to add them to config.json.")


if __name__ == "__main__":
    main()
