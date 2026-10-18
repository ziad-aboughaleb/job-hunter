"""The command line: `python -m jobhunter <command>`.

    init       create config.json, cv.md, preferences.md and .env from templates (run this first)
    doctor     check that your files and settings look right
    prompt     print the exact instructions the AI will receive
    fetch      stage 1: fetch + filter jobs        -> data/candidates.json
    evaluate   stage 2: score jobs with the AI     -> data/results.json
    send       stage 3: send matches to Telegram, remember finished jobs
    run        fetch + evaluate + send, in order (what the daily schedule runs)
    discover   find company names to add to config.json (optional, needs `pip install ddgs`)
    prune      remove company names that no longer exist from config.json

This file only defines the commands. Each one calls the `run()` function of the module that does the work.
"""
import argparse
from typing import List, Optional

from jobhunter.evaluate import stage as evaluate_stage
from jobhunter.fetch import stage as fetch_stage
from jobhunter.send import stage as send_stage
from jobhunter.tools import discover, doctor, init_project, prune, show_prompt


def cmd_run(args) -> int:
    """fetch -> evaluate -> send. Every stage runs even if an earlier one failed, so `send` can report the failure."""
    codes = [fetch_stage.run(), evaluate_stage.run(), send_stage.run(dry_run=args.dry_run)]
    return 1 if any(codes) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jobhunter", description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)

    p = commands.add_parser("init", help="create config.json, cv.md, preferences.md, .env")
    p.add_argument("--preset", help=f"role preset: {', '.join(init_project.available_presets()) or 'none found'}")
    p.add_argument("--level", choices=sorted(init_project.LEVELS), help="seniority you are looking for")
    p.add_argument("--force", action="store_true", help="overwrite existing files")
    p.set_defaults(func=lambda a: init_project.run(a.preset, a.level, a.force))

    p = commands.add_parser("doctor", help="check your files and settings")
    p.set_defaults(func=lambda a: doctor.run())

    p = commands.add_parser("prompt", help="print the exact instructions the AI will receive")
    p.add_argument("--hide-cv", action="store_true", help="show placeholders instead of your CV and preferences")
    p.set_defaults(func=lambda a: show_prompt.run(hide_cv=a.hide_cv))

    p = commands.add_parser("fetch", help="fetch and filter jobs")
    p.add_argument("--ignore-seen", action="store_true", help="do not skip jobs already dealt with (for testing)")
    p.add_argument("--no-boards", action="store_true", help="only poll the companies in config.json (no aggregators)")
    p.set_defaults(func=lambda a: fetch_stage.run(ignore_seen=a.ignore_seen, no_boards=a.no_boards))

    p = commands.add_parser("evaluate", help="score the fetched jobs with the AI")
    p.add_argument("--model", help="override llm.model from config.json")
    p.add_argument("--out", default="results.json", help="output file inside data/ (default results.json)")
    p.add_argument("--limit", type=int, default=0, help="only evaluate the first N jobs")
    p.set_defaults(func=lambda a: evaluate_stage.run(model=a.model, out=a.out, limit=a.limit))

    p = commands.add_parser("send", help="send matches to Telegram")
    p.add_argument("--test", action="store_true", help="send a test message and exit")
    p.add_argument("--check", action="store_true", help="only validate results.json")
    p.add_argument("--dry-run", action="store_true", help="print the messages; send nothing, save nothing")
    p.set_defaults(func=lambda a: send_stage.run(dry_run=a.dry_run, check_only=a.check, test=a.test))

    p = commands.add_parser("run", help="fetch + evaluate + send")
    p.add_argument("--dry-run", action="store_true", help="print the messages instead of sending them")
    p.set_defaults(func=cmd_run)

    p = commands.add_parser("discover", help="find company names to add to config.json")
    p.add_argument("--write", action="store_true", help="add the new names to config.json")
    p.add_argument("--only", default="", help="comma-separated platforms, e.g. workable,recruitee")
    p.add_argument("--max-topics", type=int, default=6, help="how many config titles to search for")
    p.add_argument("--include-generic", action="store_true", help="also search generic titles like 'engineer'")
    p.add_argument("--results", type=int, default=30, help="results per search")
    p.add_argument("--delay", type=float, default=2.0, help="seconds between searches")
    p.add_argument("--recent", action="store_true", help="only postings from the last month")
    p.set_defaults(func=lambda a: discover.run(a.write, a.only, a.max_topics, a.include_generic,
                                               a.results, a.delay, a.recent))

    p = commands.add_parser("prune", help="remove company names that returned 404 from config.json")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=lambda a: prune.run(dry_run=a.dry_run))
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)
