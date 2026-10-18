"""Deciding which jobs are matches, and which jobs are finished.

load_results()    read data/results.json and validate it (never trust the file blindly)
select_matches()  matches sorted best first, split into "send now" and "held back by the message cap"
record_seen()     mark finished jobs in data/seen.json

The rule that protects you from losing jobs lives in record_seen():
    - jobs that were evaluated and did not match are finished
    - matches are finished only AFTER they were delivered
    - jobs that were not evaluated, failed to send, or were held back by the cap are NOT marked,
      so they are tried again on the next run.
"""
import json
from typing import Any, Dict, List, Set, Tuple

from jobhunter.helpers import store


def load_results(candidates: List[Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    """Read data/results.json. Returns ({ref: result}, problems).

    Anything that does not make sense (unknown ref, duplicate, score that is not a number) is reported and
    skipped, never trusted. Jobs without a valid result are listed as "not evaluated".
    """
    try:
        raw = store.read_data("results.json", None)
    except json.JSONDecodeError as exc:
        return {}, [f"results.json is not valid JSON: {exc}"]
    if raw is None:
        return {}, ["results.json does not exist: the evaluate step did not write it"]
    if isinstance(raw, dict):
        raw = raw.get("results", [])
    if not isinstance(raw, list):
        return {}, ["results.json must be a JSON list of objects"]

    valid_refs = {c["ref"] for c in candidates}
    results: Dict[str, Dict[str, Any]] = {}
    problems: List[str] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            problems.append(f"entry {index} is not an object")
            continue
        ref = str(entry.get("ref", "")).strip().upper()
        if ref not in valid_refs:
            problems.append(f"entry {index}: unknown ref {ref!r}")
            continue
        if ref in results:
            problems.append(f"duplicate ref {ref} (first one kept)")
            continue
        try:
            score = int(round(float(str(entry.get("score")).replace("%", "").strip())))
        except (TypeError, ValueError):
            problems.append(f"{ref}: score is not a number")
            continue
        hard_fail = entry.get("hard_fail")
        if hard_fail in (None, "", False) or str(hard_fail).strip().lower() in ("null", "none"):
            hard_fail = None
        results[ref] = {
            "ref": ref, "score": max(0, min(100, score)),
            "hard_fail": str(hard_fail).strip() if hard_fail else None,
            "strengths": _as_list(entry.get("strengths")), "gaps": _as_list(entry.get("gaps")),
            "pitch": str(entry.get("pitch") or "").strip(),
        }
    missing = [c["ref"] for c in candidates if c["ref"] not in results]
    if missing:
        problems.append("not evaluated: " + ", ".join(missing))
    return results, problems


def _as_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(x) for x in value if str(x).strip()]
    return [str(value)] if value else []


def is_match(result: Dict[str, Any], threshold: int) -> bool:
    return result["score"] >= threshold and not result["hard_fail"]


def select_matches(results: Dict[str, Dict[str, Any]], threshold: int, cap: int):
    """Matches sorted best first, split into (to send now, held back by the message cap)."""
    matches = sorted((r for r in results.values() if is_match(r, threshold)), key=lambda r: -r["score"])
    return matches[:cap], matches[cap:]


def record_seen(candidates: List[Dict[str, Any]], results: Dict[str, Dict[str, Any]],
                sent: Set[str], threshold: int, retention_days: int) -> None:
    """Mark finished jobs in seen.json (see the module docstring for what counts as finished)."""
    seen = store.load_seen()
    today = store.today()
    for job in candidates:
        result = results.get(job["ref"])
        if result is None:
            continue
        if not is_match(result, threshold) or job["ref"] in sent:
            seen[job["uid"]] = today
    store.save_seen(seen, retention_days)
