#!/usr/bin/env python3
"""
Remove company boards that returned 404 ("board not found") in the last fetch_jobs.py run
from config.json, so they stop showing up as errors.

    python3 prune_companies.py --dry-run     # show what would be removed
    python3 prune_companies.py               # remove them from config.json

Reads run_status.json, so run fetch_jobs.py first. Only 404s are removed, never network failures.
"""
import argparse
import json

from common import ROOT, load_json, save_json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    status = load_json("run_status.json", None)
    if not status:
        raise SystemExit("run_status.json not found - run fetch_jobs.py first.")
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))

    removed = []
    for err in status.get("errors", []):
        if "board not found" not in err:
            continue
        source, slug = err.split(":", 1)[0].split("/", 1)
        names = cfg.get("companies", {}).get(source, [])
        keep = [n for n in names if n.strip().lower() != slug.strip().lower()]
        if len(keep) != len(names):
            cfg["companies"][source] = keep
            removed.append(f"{source}/{slug}")

    print(f"{'Would remove' if args.dry_run else 'Removed'} {len(removed)} board(s):")
    for r in removed:
        print("  -", r)
    if removed and not args.dry_run:
        save_json("config.json", cfg)
        print("config.json updated.")


if __name__ == "__main__":
    main()
