#!/usr/bin/env python3
"""
Stage 3 - validate results.json, send matching jobs to Telegram, then record
what was evaluated in seen.json. Standard library only.

Usage:
    python3 send_telegram.py --test      # send a test message and exit
    python3 send_telegram.py --check     # validate results.json only (no sending)
    python3 send_telegram.py --dry-run   # print the cards, send nothing, don't touch seen.json
    python3 send_telegram.py             # normal run
"""
import argparse
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

from common import (load_config, load_env, load_json, load_seen, prune_seen,
                    save_json, today_str)


# --------------------------------------------------------------------------- #
# Telegram
# --------------------------------------------------------------------------- #
def tg_send(token, chat_id, text, preview=False):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": not preview,
    }).encode("utf-8")
    last = "unknown error"
    for _ in range(4):
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20):
                return True, ""
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            try:
                info = json.loads(body)
            except json.JSONDecodeError:
                info = {}
            if exc.code == 429:  # rate limited: wait as instructed, retry
                wait = int(info.get("parameters", {}).get("retry_after", 5))
                time.sleep(min(wait, 60) + 1)
                last = "rate limited"
                continue
            return False, f"HTTP {exc.code}: {info.get('description', body[:200])}".replace(token, "***")
        except Exception as exc:  # network error
            last = str(exc).replace(token, "***")
            time.sleep(2)
    return False, last


# --------------------------------------------------------------------------- #
# Formatting (everything user/LLM-supplied is HTML-escaped)
# --------------------------------------------------------------------------- #
def esc(value, limit=None):
    text = str(value or "").strip()
    if limit and len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return html.escape(text, quote=False)


def format_card(c, r):
    lines = [
        f'{"⭐ " if c.get("priority") else ""}🟢 <b><a href="{html.escape(c["url"], quote=True)}">{esc(c["title"], 120)} — {esc(c["company"], 60)}</a></b>',
        f'• <b>Match Score:</b> {r["score"]}%',
        f'• <b>Location:</b> {esc(c["location"] or "Remote", 120)}',
    ]
    if c.get("posted"):
        lines.append(f'• <b>Posted:</b> {esc(c["posted"])}')
    lines += ["", "<b>Why It Matches:</b>"]
    lines += [f"• {esc(x, 250)}" for x in r["strengths"][:3]] or ["• (none listed)"]
    lines += ["", "<b>Skill Gaps:</b>"]
    lines += [f"• {esc(x, 250)}" for x in r["gaps"][:3]] or ["• None"]
    if r["pitch"]:
        lines += ["", "<b>Tailored Pitch Line:</b>", f'<i>"{esc(r["pitch"], 400)}"</i>']
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# results.json validation
# --------------------------------------------------------------------------- #
def as_list(value):
    if isinstance(value, list):
        return [str(x) for x in value if str(x).strip()]
    return [str(value)] if value else []


def load_results(candidates):
    """Return ({ref: normalized_result}, [problems])."""
    try:
        raw = load_json("results.json", None)
    except json.JSONDecodeError as exc:
        return {}, [f"results.json is not valid JSON: {exc}"]
    if raw is None:
        return {}, ["results.json does not exist - the evaluation step did not write it"]
    if isinstance(raw, dict):
        raw = raw.get("results", [])
    if not isinstance(raw, list):
        return {}, ["results.json must be a JSON list of objects"]

    valid_refs = {c["ref"] for c in candidates}
    out, problems = {}, []
    for i, r in enumerate(raw):
        if not isinstance(r, dict):
            problems.append(f"entry {i} is not an object")
            continue
        ref = str(r.get("ref", "")).strip().upper()
        if ref not in valid_refs:
            problems.append(f"entry {i}: unknown ref {ref!r}")
            continue
        if ref in out:
            problems.append(f"duplicate ref {ref} (first one kept)")
            continue
        try:
            score = int(round(float(str(r.get("score")).replace("%", "").strip())))
        except (TypeError, ValueError):
            problems.append(f"{ref}: score is not a number")
            continue
        hard = r.get("hard_fail")
        hard = None if hard in (None, "", False) or str(hard).strip().lower() in ("null", "none") else str(hard).strip()
        out[ref] = {
            "ref": ref,
            "score": max(0, min(100, score)),
            "hard_fail": hard,
            "strengths": as_list(r.get("strengths")),
            "gaps": as_list(r.get("gaps")),
            "pitch": str(r.get("pitch") or "").strip(),
        }
    missing = [c["ref"] for c in candidates if c["ref"] not in out]
    if missing:
        problems.append("not evaluated: " + ", ".join(missing))
    return out, problems


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    load_env()
    cfg = load_config()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    preview = cfg["telegram"]["link_preview"]
    offline = args.check or args.dry_run

    if not offline and not (token and chat_id):
        sys.exit("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing. Copy .env.example to .env and fill it in.")

    def notify(text):
        if args.dry_run:
            print("-" * 60 + "\n" + html.unescape(re.sub(r"<[^>]+>", "", text)) + "\n")
            return True, ""
        return tg_send(token, chat_id, text, preview)

    if args.test:
        ok, err = tg_send(token, chat_id, "✅ <b>Job hunter</b>: Telegram connection works.", preview)
        print("Test message sent." if ok else f"Failed: {err}")
        sys.exit(0 if ok else 1)

    # ---- load inputs ----
    try:
        candidates = load_json("candidates.json", None)
    except json.JSONDecodeError:
        candidates = None
    status = load_json("run_status.json", {}) or {}

    if candidates is None:
        msg = "⚠️ <b>Job scan failed</b>: candidates.json is missing - the fetch step did not run or crashed."
        print(html.unescape(re.sub(r"<[^>]+>", "", msg)))
        if not args.check:
            notify(msg)
        sys.exit(1)

    errors = status.get("errors", [])
    header = (f"Fetched {status.get('fetched', '?')} jobs from "
              f"{status.get('companies_ok', '?')}/{status.get('companies_total', '?')} boards")

    if not candidates:
        print("No candidates today.")
        if not args.check and cfg["telegram"]["notify_on_empty"]:
            extra = f"\n⚠️ {len(errors)} board(s) failed: {esc('; '.join(errors[:3]), 300)}" if errors else ""
            notify(f"📭 <b>Job scan</b>: no new jobs passed the filters.\n{esc(header)}{extra}")
        sys.exit(0)

    results, problems = load_results(candidates)
    for p in problems:
        print(f"  ! {p}", file=sys.stderr)
    if args.check:
        print("results.json looks valid." if not problems else f"{len(problems)} problem(s) found.")
        sys.exit(1 if problems else 0)

    # ---- decide what to send ----
    by_ref = {c["ref"]: c for c in candidates}
    threshold = cfg["score_threshold"]
    matches = sorted(
        (r for r in results.values() if r["score"] >= threshold and not r["hard_fail"]),
        key=lambda r: -r["score"],
    )
    cap = cfg["limits"]["max_messages"]
    to_send, deferred = matches[:cap], matches[cap:]

    sent_ok, failed = set(), []
    for r in to_send:
        ok, err = notify(format_card(by_ref[r["ref"]], r))
        if ok:
            sent_ok.add(r["ref"])
        else:
            failed.append(f"{r['ref']}: {err}")
            print(f"  ! Telegram send failed for {r['ref']}: {err}", file=sys.stderr)
        time.sleep(1)

    # ---- update seen.json (never in dry-run) ----
    # Evaluated non-matches are done. Matches count only once delivered.
    # Unevaluated jobs, failed sends and over-cap matches are retried next run.
    if not args.dry_run:
        seen = load_seen()
        today = today_str()
        for c in candidates:
            r = results.get(c["ref"])
            if not r:
                continue
            is_match = r["score"] >= threshold and not r["hard_fail"]
            if not is_match or c["ref"] in sent_ok:
                seen[c["uid"]] = today
        save_json("seen.json", prune_seen(seen, cfg["limits"]["seen_retention_days"]))

    # ---- summary ----
    summary = [
        "📊 <b>Job scan</b>",
        f"{esc(header)}",
        f"Passed filters: {len(candidates)} · evaluated: {len(results)} · "
        f"matches ≥{threshold}%: {len(matches)} · sent: {len(sent_ok)}",
    ]
    if not matches:
        summary.append("No strong matches today.")
    if deferred:
        summary.append(f"⏭ {len(deferred)} more match(es) held back by the message cap; they will be sent next run.")
    warnings = list(problems) + failed
    if errors:
        warnings.append(f"{len(errors)} board(s) failed to load")
    if warnings:
        summary.append("⚠️ " + esc("; ".join(warnings), 600))
    notify("\n".join(summary))

    sys.exit(1 if (failed or problems) else 0)


if __name__ == "__main__":
    main()
