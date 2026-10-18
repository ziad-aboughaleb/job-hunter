"""Stage 1: fetch jobs from every configured source, filter them, write data/candidates.json.

Steps (each is one function below):
    build_targets   decide what to fetch (companies + aggregator boards from config.json)
    fetch_one       fetch one target; never raises, so one broken site cannot stop the run
    collect         apply "already seen" + the filters, remove duplicates
    rank            put priority companies first, then best stack overlap, then newest; apply the cap
    run             glue: do all of the above and write the output files
"""
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from jobhunter.helpers import store
from jobhunter.helpers.config import board_options, load_config
from jobhunter.fetch.filters import JobFilter
from jobhunter.helpers.models import Job
from jobhunter.fetch.sources import BOARD_SOURCES, COMPANY_SOURCES


@dataclass
class Target:
    """One thing to fetch: a company's board, or an aggregator."""
    source: str  # "greenhouse", "remotive", ...
    name: str  # the company name, or the aggregator name
    fetch: Callable[[], Optional[List[Job]]]


@dataclass
class Collected:
    candidates: List[Job] = field(default_factory=list)
    dropped: Counter = field(default_factory=Counter)  # reason -> how many jobs
    sources_total: int = 0
    sources_ok: int = 0
    jobs_fetched: int = 0
    errors: List[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
def _unique_names(names: List[str]) -> List[str]:
    """Drop duplicates that differ only by case ('Tempo' / 'tempo'); the first spelling wins."""
    unique: Dict[str, str] = {}
    for name in names:
        if name.strip():
            unique.setdefault(name.strip().lower(), name.strip())
    return list(unique.values())


def build_targets(cfg: Dict[str, Any], include_boards: bool = True) -> Tuple[List[Target], List[str]]:
    """Turn config.json into a list of things to fetch. Also returns config problems found on the way."""
    targets: List[Target] = []
    problems: List[str] = []

    for source, names in cfg["companies"].items():
        fetcher = COMPANY_SOURCES.get(source)
        if fetcher is None:
            problems.append(f"unknown company source '{source}' in config.json "
                            f"(choose from: {', '.join(COMPANY_SOURCES)})")
            continue
        for name in _unique_names(names):
            targets.append(Target(source, name, lambda fn=fetcher, n=name: fn(n)))

    if include_boards:
        for name, value in cfg["boards"].items():
            options = board_options(value)
            if not options["enabled"]:
                continue
            fetcher = BOARD_SOURCES.get(name)
            if fetcher is None:
                problems.append(f"unknown board '{name}' in config.json (choose from: {', '.join(BOARD_SOURCES)})")
                continue
            targets.append(Target(name, name, lambda fn=fetcher, o=options: fn(o)))
    return targets, problems


def fetch_one(target: Target) -> Tuple[Target, Optional[List[Job]], Optional[str]]:
    """Fetch one target. Returns (target, jobs, error). Exactly one of jobs / error is set."""
    label = f"{target.source}/{target.name}"
    try:
        jobs = target.fetch()
    except Exception as exc:  # a broken site must not stop the other 200
        return target, None, f"{label}: {exc}"
    if jobs is None:
        return target, None, f"{label}: board not found (404) - check the slug"
    return target, jobs, None


def collect(outcomes: List[Tuple[Target, Optional[List[Job]], Optional[str]]],
            seen: Dict[str, str], job_filter: JobFilter) -> Collected:
    """Go through every fetched job and keep the ones that pass: not seen, passes the filters, not a duplicate."""
    result = Collected()
    same_job: Set[Tuple[str, str]] = set()  # (company, title): the same job listed on two sites
    for target, jobs, error in outcomes:
        result.sources_total += 1
        if error:
            result.errors.append(error)
            continue
        result.sources_ok += 1
        result.jobs_fetched += len(jobs)
        for job in jobs:
            if not job.url:
                result.dropped["no_url"] += 1
            elif job.uid in seen:
                result.dropped["already_seen"] += 1
            else:
                reason = job_filter.reject_reason(job)
                if reason:
                    result.dropped[reason] += 1
                elif (job.company.lower(), job.title.lower()) in same_job:
                    result.dropped["duplicate"] += 1
                else:
                    same_job.add((job.company.lower(), job.title.lower()))
                    result.candidates.append(job)
    return result


def rank(candidates: List[Job], cap: int) -> Tuple[List[Job], int]:
    """Order jobs and apply the per-run cap. Returns (jobs to evaluate, how many were cut by the cap).

    Priority-company jobs come first and are never cut. The rest are ordered by stack overlap, then newest.
    """
    def best_first(job: Job):
        return (-job.stack_hits, -(job.posted.timestamp() if job.posted else 0))

    priority = sorted((j for j in candidates if j.priority), key=best_first)
    others = sorted((j for j in candidates if not j.priority), key=best_first)
    return priority + others[:cap], max(0, len(others) - cap)


def to_record(job: Job, ref: str, max_chars: int) -> Dict[str, Any]:
    """The JSON form of a job written to candidates.json. `ref` ("J1", "J2", ...) is how results refer back to it."""
    return {
        "ref": ref, "uid": job.uid, "company": job.company, "title": job.title, "url": job.url,
        "location": job.location, "posted": job.posted.date().isoformat() if job.posted else "",
        "priority": job.priority, "stack_hits": job.stack_hits,
        "description": job.description[:max_chars],
    }


# --------------------------------------------------------------------------- #
def run(ignore_seen: bool = False, no_boards: bool = False) -> int:
    """The `fetch` command. Returns the process exit code."""
    cfg = load_config()
    limits = cfg["limits"]
    seen = {} if ignore_seen else store.load_seen()

    # Remove last run's outputs first, so a failed run can never be mistaken for a fresh one.
    store.delete_data("candidates.json", "results.json", "run_status.json")

    targets, problems = build_targets(cfg, include_boards=not no_boards)
    with ThreadPoolExecutor(max_workers=max(1, int(limits["fetch_workers"]))) as pool:
        outcomes = list(pool.map(fetch_one, targets))

    collected = collect(outcomes, seen, JobFilter(cfg["filters"]))
    chosen, over_cap = rank(collected.candidates, limits["max_candidates_per_run"])
    records = [to_record(job, f"J{i}", limits["description_max_chars"]) for i, job in enumerate(chosen, start=1)]
    errors = problems + collected.errors

    store.write_data("candidates.json", records)
    store.write_data("run_status.json", {
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources_total": collected.sources_total, "sources_ok": collected.sources_ok,
        "fetched": collected.jobs_fetched, "passed_filters": len(records),
        "deferred_over_cap": over_cap, "dropped": dict(collected.dropped), "errors": errors,
    })

    print(f"Sources: {collected.sources_ok}/{collected.sources_total} reachable | jobs fetched: {collected.jobs_fetched}")
    print(f"Dropped: {dict(collected.dropped) or 'nothing'}")
    print(f"Candidates written to data/candidates.json: {len(records)}"
          + (f" (+{over_cap} over the cap, they come back next run)" if over_cap else ""))
    for error in errors:
        print(f"  ! {error}", file=sys.stderr)

    if collected.sources_total == 0:
        print("Nothing to fetch: enable a board or add companies in config.json.", file=sys.stderr)
        return 2
    if collected.sources_ok == 0:
        print("Every source failed. Check your network connection and config.json.", file=sys.stderr)
        return 2
    return 0
