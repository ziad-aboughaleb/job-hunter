#!/usr/bin/env python3
"""
Optional helper: find company board slugs to put in config.json.

Runs your original "site:" searches once, extracts the company slug from each
result URL, and prints the ones that are not in config.json yet.
Run this by hand (e.g. weekly), NOT in the daily cron.

    pip install ddgs
    python3 discover_companies.py            # just print suggestions
    python3 discover_companies.py --write    # also append them to config.json
"""
import argparse
import json
import re
import time

from common import ROOT, load_config, save_json

try:
    from ddgs import DDGS
except ImportError:  # old package name
    from duckduckgo_search import DDGS

SITES = {
    "greenhouse": ["job-boards.greenhouse.io", "boards.greenhouse.io"],
    "lever": ["jobs.lever.co"],
    "ashby": ["jobs.ashbyhq.com"],
}
TOPICS = ['"react" remote', '"frontend" remote', '"full-stack" remote', '"mern" remote']
PATTERNS = {
    "greenhouse": re.compile(r"greenhouse\.io/(?:embed/job_app\?for=)?([A-Za-z0-9_-]+)"),
    "lever": re.compile(r"jobs\.lever\.co/([A-Za-z0-9_.-]+)"),
    "ashby": re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_.%-]+)"),
}
IGNORE = {"embed", "jobs", "job_app", "www"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="append new slugs to config.json")
    args = ap.parse_args()

    cfg = load_config()
    known = {src: set(cfg["companies"].get(src, [])) for src in PATTERNS}
    found = {src: set() for src in PATTERNS}
    ddgs = DDGS()

    for source, hosts in SITES.items():
        for host in hosts:
            for topic in TOPICS:
                query = f"site:{host} {topic}"
                print(f"Searching: {query}")
                try:
                    for r in ddgs.text(query, max_results=30):
                        match = PATTERNS[source].search(r.get("href", ""))
                        if match and match.group(1).lower() not in IGNORE:
                            found[source].add(match.group(1))
                except Exception as exc:
                    print(f"  search failed: {exc}")
                time.sleep(10)

    new = {src: sorted(found[src] - known[src]) for src in found}
    print("\nNew company slugs:")
    for src, slugs in new.items():
        print(f"  {src}: {slugs or '-'}")

    if args.write and any(new.values()):
        path = ROOT / "config.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for src, slugs in new.items():
            data.setdefault("companies", {}).setdefault(src, []).extend(slugs)
        save_json("config.json", data)
        print("\nconfig.json updated.")


if __name__ == "__main__":
    main()
