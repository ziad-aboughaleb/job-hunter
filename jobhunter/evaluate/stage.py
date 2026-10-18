"""Stage 2: one independent model request per job; results are written after every job.

Why one request per job: nothing accumulates between jobs, so the context can never overflow, a failure affects one
job only, and no tool-calling or agent framework is involved.

    run()           the `evaluate` command: load candidates, CV and preferences, loop over the jobs
    evaluate_job()  score one job, with one corrective retry if the reply is unusable
"""
import json
import sys
import time
from typing import Any, Dict, Optional

from jobhunter.evaluate.llm import LLMClient, LLMFatal, LLMUnavailable, TruncatedOutput
from jobhunter.evaluate.parsing import normalize, parse_json_text
from jobhunter.evaluate.prompt import build_system_prompt, build_user_message
from jobhunter.helpers import store
from jobhunter.helpers.config import load_config, load_env

CHARS_PER_TOKEN = 3  # rough; used only to keep a job inside the model's context window
OUTPUT_RESERVE_CHARS = 3000
MAX_CONSECUTIVE_FAILURES = 5


def evaluate_job(client: LLMClient, system: str, job: Dict[str, Any], max_description_chars: int) -> Dict[str, Any]:
    """Score one job. One corrective retry if the reply is unusable."""
    user = build_user_message(job, max_description_chars)
    last_error: Optional[Exception] = None
    reply = ""
    for attempt in range(2):
        prompt = user
        if attempt:
            prompt += (f"\n\nIMPORTANT: your previous reply was unusable ({last_error}). "
                       "Reply again with ONLY the JSON object, nothing else.")
        try:
            reply = client.complete(system, prompt)
            return normalize(parse_json_text(reply), job["ref"])
        except (ValueError, KeyError, TypeError) as exc:  # includes JSONDecodeError and TruncatedOutput
            last_error = exc
            if isinstance(exc, TruncatedOutput):
                client.grow_output_budget()  # give the retry, and later jobs, more room
    snippet = (reply or "")[:150].replace("\n", " ")
    raise ValueError(f"invalid model output twice ({last_error}); last reply started: {snippet!r}")


def run(model: Optional[str] = None, out: str = "results.json", limit: int = 0) -> int:
    """The `evaluate` command. Returns the process exit code."""
    load_env()
    cfg = load_config()
    llm_cfg = cfg["llm"]

    try:
        candidates = store.read_data("candidates.json", None)
    except json.JSONDecodeError:
        candidates = None
    if candidates is None:
        print("data/candidates.json is missing or invalid. Run `python -m jobhunter fetch` first.", file=sys.stderr)
        return 1
    if not candidates:
        store.write_data(out, [])
        print("No candidates to evaluate.")
        return 0

    cv, preferences = store.read_text("cv.md"), store.read_text("preferences.md")
    if len(cv) < 400 or cv.lstrip().startswith("<!--"):
        print("cv.md is empty or still the placeholder: paste your CV into it first.", file=sys.stderr)
        return 1
    if "<FILL IN" in preferences:
        print("WARNING: preferences.md still has <FILL IN> placeholders; scoring will be less accurate.", file=sys.stderr)

    system = build_system_prompt(cfg, cv, preferences)
    if len(system) > llm_cfg["num_ctx"] * CHARS_PER_TOKEN - 4000:
        print("WARNING: CV + preferences are large for this num_ctx; raise llm.num_ctx in config.json.", file=sys.stderr)
    client = LLMClient(llm_cfg, model)

    jobs = candidates[:limit] if limit else candidates
    store.write_data(out, [])  # never leave a previous run's results behind: refs like J1 repeat every run
    results, failed, streak = [], [], 0
    print(f"Evaluating {len(jobs)} job(s) with {client.model} via {client.provider} (one request per job)...")

    for i, job in enumerate(jobs, start=1):
        started = time.time()
        budget = max(1500, llm_cfg["num_ctx"] * CHARS_PER_TOKEN - len(system) - OUTPUT_RESERVE_CHARS)
        try:
            result = evaluate_job(client, system, job, budget)
        except LLMUnavailable as exc:
            print(f"Cannot reach {client.base_url} ({exc})."
                  + (" Is Ollama running? Try: ollama serve" if client.provider == "ollama" else " Check your network."),
                  file=sys.stderr)
            return 1
        except LLMFatal as exc:
            print(f"Stopping: {exc}", file=sys.stderr)
            return 1
        except Exception as exc:  # this job only: skip it, it is retried on the next run
            failed.append(job["ref"])
            streak += 1
            print(f"[{i}/{len(jobs)}] {job['ref']} FAILED: {exc}", file=sys.stderr)
            if streak >= MAX_CONSECUTIVE_FAILURES:
                print(f"Stopping early: {MAX_CONSECUTIVE_FAILURES} jobs in a row failed, so the model or settings are "
                      "the problem (try another model, a larger llm.max_output_tokens, or llm.json_mode).",
                      file=sys.stderr)
                break
            continue
        streak = 0
        results.append(result)
        store.write_data(out, results)  # after every job, so an interrupted run keeps its progress
        label = f"hard_fail: {result['hard_fail']}" if result["hard_fail"] else f"score {result['score']}"
        print(f"[{i}/{len(jobs)}] {job['ref']} {job['title'][:45]!r} -> {label} ({time.time() - started:.0f}s)")
        if llm_cfg["request_delay"] and i < len(jobs):
            time.sleep(llm_cfg["request_delay"])  # stay under free-tier rate limits

    print(f"Done: {len(results)} evaluated, {len(failed)} failed (failed jobs are retried next run).")
    return 1 if failed else 0
