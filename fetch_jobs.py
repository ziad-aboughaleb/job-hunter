#!/usr/bin/env python3
"""
Stage 1 - fetch jobs from the public Greenhouse / Lever / Ashby APIs,
apply hard filters, drop jobs already evaluated, write candidates.json.
Sources: Greenhouse, Lever, Ashby, Recruitee, Workable, Personio (per company) and
Remotive / RemoteOK / Arbeitnow (aggregators).

Standard library only (no pip install needed).

Usage:
    python3 fetch_jobs.py                  # normal daily run
    python3 fetch_jobs.py --ignore-seen    # testing: don't skip already-seen jobs
    python3 fetch_jobs.py --no-boards      # extra runs: only your listed companies (fast, no aggregator calls)
"""
import argparse
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timedelta, timezone

from common import ROOT, load_config, load_seen, save_json

UA = "Mozilla/5.0 (compatible; personal-job-hunter/1.0)"


# --------------------------------------------------------------------------- #
# HTTP + text helpers
# --------------------------------------------------------------------------- #
def http_get_text(url, accept="*/*", retries=2, timeout=25):
    """GET text. Returns None on 404 (unknown company). Raises on other failures."""
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            last = exc
        except Exception as exc:  # network errors, timeouts
            last = exc
        time.sleep(1.5 * (attempt + 1))
    raise last


def http_get_json(url, **kwargs):
    text = http_get_text(url, accept="application/json", **kwargs)
    return None if text is None else json.loads(text)


def clean_html(raw):
    text = html.unescape(raw or "")  # Greenhouse returns HTML-escaped HTML
    text = re.sub(r"(?i)<\s*(br|/p|/div|/li|/h[1-6]|/ul|/ol)\s*/?>", "\n", text)
    text = re.sub(r"(?i)<li[^>]*>", "- ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def parse_date(value):
    """Handles ISO strings, '2026-07-27 14:23:51 UTC', '+0000' offsets, date-only values and epoch milliseconds."""
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        text = str(value).strip()
        text = re.sub(r"\s*UTC$", "+00:00", text)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        text = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", text)
        frac = re.search(r"\.(\d+)", text)
        if frac:  # older Pythons need exactly 3 or 6 fractional digits
            text = text.replace(frac.group(0), "." + (frac.group(1) + "000000")[:6], 1)
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (ValueError, OSError, OverflowError):
        return None


def pretty_company(slug):
    return slug.replace("-", " ").replace("_", " ").title()


# --------------------------------------------------------------------------- #
# One fetcher per ATS. Each returns a list of normalized dicts, or None if the
# board does not exist.
# --------------------------------------------------------------------------- #
def fetch_greenhouse(slug):
    data = http_get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
    if data is None:
        return None
    jobs = []
    for j in data.get("jobs", []):
        jobs.append({
            "job_id": str(j.get("id", "")),
            "title": j.get("title", "") or "",
            "url": j.get("absolute_url", "") or "",
            "location": (j.get("location") or {}).get("name", "") or "",
            "remote_flag": None,
            "posted": parse_date(j.get("first_published") or j.get("updated_at")),
            "description": clean_html(j.get("content", "")),
        })
    return jobs


def fetch_lever(slug, eu=False):
    host = "api.eu.lever.co" if eu else "api.lever.co"
    data = http_get_json(f"https://{host}/v0/postings/{slug}?mode=json")
    if data is None:
        return None
    jobs = []
    for j in data if isinstance(data, list) else []:
        cats = j.get("categories") or {}
        location = cats.get("location") or ", ".join(cats.get("allLocations") or [])
        parts = [j.get("descriptionPlain", "")]
        for block in j.get("lists") or []:
            parts.append(f"{block.get('text', '')}\n{clean_html(block.get('content', ''))}")
        parts.append(j.get("additionalPlain", ""))
        jobs.append({
            "job_id": str(j.get("id", "")),
            "title": j.get("text", "") or "",
            "url": j.get("hostedUrl", "") or "",
            "location": location or "",
            "remote_flag": True if str(j.get("workplaceType", "")).lower() == "remote" else None,
            "posted": parse_date(j.get("createdAt")),
            "description": "\n\n".join(p for p in parts if p).strip(),
        })
    return jobs


def fetch_ashby(slug):
    data = http_get_json(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    if data is None:
        return None
    jobs = []
    for j in data.get("jobs", []):
        if j.get("isListed") is False:
            continue
        secondary = []
        for s in j.get("secondaryLocations") or []:
            secondary.append(s.get("location", "") if isinstance(s, dict) else str(s))
        location = ", ".join(x for x in [j.get("location", "")] + secondary if x)
        remote = bool(j.get("isRemote")) or str(j.get("workplaceType", "")).lower() == "remote"
        jobs.append({
            "job_id": str(j.get("id", "")),
            "title": j.get("title", "") or "",
            "url": j.get("jobUrl") or j.get("applyUrl") or "",
            "location": location,
            "remote_flag": True if remote else None,
            "posted": parse_date(j.get("publishedAt") or j.get("publishedDate")),
            "description": j.get("descriptionPlain") or clean_html(j.get("descriptionHtml", "")),
        })
    return jobs


REMOTE_PHRASES = ("fully remote", "100% remote", "remote-first", "remote first", "work from anywhere",
                  "work remotely", "remote position", "remote role")


def looks_remote(location, title, description):
    """For ATSs with no remote flag (Personio): remote in the office/title, or an explicit phrase near the top."""
    if "remote" in f"{location} {title}".lower():
        return True
    head = description[:1500].lower()
    return any(p in head for p in REMOTE_PHRASES)


def fetch_recruitee(slug):
    data = http_get_json(f"https://{slug}.recruitee.com/api/offers/")
    if data is None:
        return None
    jobs = []
    for j in data.get("offers", []):
        location = j.get("location") or ", ".join(x for x in (j.get("city"), j.get("country")) if x)
        description = "\n\n".join(x for x in (clean_html(j.get("description", "")),
                                               clean_html(j.get("requirements", ""))) if x)
        jobs.append({
            "job_id": str(j.get("id") or j.get("guid") or j.get("slug") or ""),
            "title": j.get("title", "") or "",
            "company": j.get("company_name") or pretty_company(slug),
            "url": j.get("careers_url") or j.get("url") or "",
            "location": location or "",
            "remote_flag": True if j.get("remote") else None,
            "posted": parse_date(j.get("published_at") or j.get("created_at")),
            "description": description,
        })
    return jobs


def fetch_workable(slug):
    data = http_get_json(f"https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true")
    if not isinstance(data, dict):
        return None
    company = data.get("name") or pretty_company(slug)
    jobs = []
    for j in data.get("jobs", []):
        loc_obj = j.get("location") if isinstance(j.get("location"), dict) else {}
        parts = [j.get("city") or loc_obj.get("city"), j.get("state") or loc_obj.get("region"),
                 j.get("country") or loc_obj.get("country")]
        location = ", ".join(p for p in parts if p)
        if not location:  # fall back to the locations list
            names = []
            for loc in j.get("locations") or []:
                if isinstance(loc, dict):
                    names.append(", ".join(x for x in (loc.get("city"), loc.get("region"), loc.get("country")) if x))
            location = " / ".join(n for n in names if n)
        remote = bool(j.get("telecommuting")) or bool(loc_obj.get("telecommuting"))
        jobs.append({
            "job_id": str(j.get("shortcode") or j.get("id") or j.get("code") or ""),
            "title": j.get("title", "") or "",
            "company": company,
            "url": j.get("url") or j.get("shortlink") or j.get("application_url") or "",
            "location": location,
            "remote_flag": True if remote else None,
            "posted": parse_date(j.get("published_on") or j.get("created_at")),
            "description": clean_html(j.get("description") or j.get("full_description") or ""),
        })
    return jobs


def fetch_personio(slug):
    text = base = None
    for domain in ("de", "com"):  # a company's feed lives on one of the two domains
        base = f"https://{slug}.jobs.personio.{domain}"
        text = http_get_text(f"{base}/xml?language=en", accept="application/xml,text/xml,*/*")
        if text:
            break
    if not text:
        return None
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError(f"feed is not valid XML ({exc})")
    jobs = []
    for p in root.iter("position"):
        def field(tag):
            return (p.findtext(tag) or "").strip()

        offices = [field("office")] + [(o.text or "").strip() for o in p.findall("additionalOffices/office")]
        location = ", ".join(dict.fromkeys(o for o in offices if o))
        sections = []
        for d in p.findall("jobDescriptions/jobDescription"):
            name = (d.findtext("name") or "").strip()
            value = clean_html(d.findtext("value") or "")
            if value:
                sections.append(f"{name}\n{value}" if name else value)
        facts = [f"{label}: {field(tag)}" for label, tag in (("Seniority", "seniority"),
                 ("Years of experience", "yearsOfExperience"), ("Employment", "employmentType"),
                 ("Schedule", "schedule")) if field(tag)]
        description = ("\n".join(facts) + "\n\n" if facts else "") + "\n\n".join(sections)
        title = field("name")
        jobs.append({
            "job_id": field("id"),
            "title": title,
            "company": field("subcompany") or pretty_company(slug),
            "url": f"{base}/job/{field('id')}" if field("id") else "",
            "location": location,
            "remote_flag": True if looks_remote(location, title, description) else None,
            "posted": parse_date(field("createdAt")),
            "description": description,
        })
    return jobs


# --------------------------------------------------------------------------- #
# Aggregator boards: many companies per call, no company list needed.
# Each returns a list of normalized dicts (with a per-job "company"), or None.
# Please keep to one run per day and keep the links back to the source.
# --------------------------------------------------------------------------- #
def fetch_remotive():
    data = http_get_json("https://remotive.com/api/remote-jobs?category=software-dev&limit=300")
    if data is None:
        return None
    jobs = []
    for j in data.get("jobs", []):
        jobs.append({
            "job_id": str(j.get("id", "")),
            "title": j.get("title", "") or "",
            "company": j.get("company_name", "") or "Unknown",
            "url": j.get("url", "") or "",
            "location": j.get("candidate_required_location", "") or "Remote",
            "remote_flag": True,
            "posted": parse_date(j.get("publication_date")),
            "description": clean_html(j.get("description", "")),
        })
    return jobs


def fetch_remoteok():
    data = http_get_json("https://remoteok.com/api")
    if not isinstance(data, list):
        return None
    jobs = []
    for j in data:
        if not isinstance(j, dict) or not j.get("position"):
            continue  # first element is a legal notice, not a job
        tags = ", ".join(j.get("tags") or [])
        jobs.append({
            "job_id": str(j.get("id", "") or j.get("slug", "")),
            "title": j.get("position", "") or "",
            "company": j.get("company", "") or "Unknown",
            "url": j.get("url") or j.get("apply_url") or "",
            "location": j.get("location", "") or "Remote",
            "remote_flag": True,
            "posted": parse_date(j.get("date")) or (parse_date(j["epoch"] * 1000) if j.get("epoch") else None),
            "description": (f"Tags: {tags}\n\n" if tags else "") + clean_html(j.get("description", "")),
        })
    return jobs


def fetch_arbeitnow(pages=2):
    jobs, url = [], "https://www.arbeitnow.com/api/job-board-api"
    for _ in range(pages):
        data = http_get_json(url)
        if data is None:
            return jobs or None
        for j in data.get("data", []):
            created = j.get("created_at")
            tags = ", ".join(j.get("tags") or [])
            jobs.append({
                "job_id": str(j.get("slug", "")),
                "title": j.get("title", "") or "",
                "company": j.get("company_name", "") or "Unknown",
                "url": j.get("url", "") or "",
                "location": j.get("location", "") or "",
                "remote_flag": True if j.get("remote") else None,
                "posted": parse_date(created * 1000) if isinstance(created, (int, float)) else parse_date(created),
                "description": (f"Tags: {tags}\n\n" if tags else "") + clean_html(j.get("description", "")),
            })
        url = (data.get("links") or {}).get("next")
        if not url:
            break
    return jobs


BOARD_FETCHERS = {
    "remotive": fetch_remotive,
    "remoteok": fetch_remoteok,
    "arbeitnow": fetch_arbeitnow,
}

FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "lever": lambda slug: fetch_lever(slug, eu=False),
    "lever_eu": lambda slug: fetch_lever(slug, eu=True),
    "ashby": fetch_ashby,
    "recruitee": fetch_recruitee,
    "workable": fetch_workable,
    "personio": fetch_personio,
}


# --------------------------------------------------------------------------- #
# Filtering
# --------------------------------------------------------------------------- #
def compile_keywords(words):
    return [re.compile(r"(?<!\w)" + re.escape(w.lower()) + r"(?!\w)") for w in words]


def norm(text):
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def term_in(text, term):
    """Whole-word match of `term` in `text` (both lowercase), so "usa" does not match "Lusaka",
    "uk" does not match "Ukraine", "java" does not match "JavaScript"."""
    t = term.strip().lower()
    if not t:
        return False
    before = r"(?<!\w)" if t[0].isalnum() else ""
    after = r"(?!\w)" if t[-1].isalnum() else ""
    return re.search(before + re.escape(t) + after, text) is not None


def title_excluded(title, terms):
    return any(term_in(title, t) for t in terms)


def company_matches(job, terms):
    """Case/punctuation-insensitive substring match against the company name."""
    name = norm(job["company"])
    return any(norm(t) and norm(t) in name for t in terms)


def reject_reason(job, f, patterns, now):
    """Return a short reason string if the job should be dropped, else None.
    Also sets job["priority"] and job["stack_hits"]."""
    title = job["title"].lower()
    loc = job["location"].lower()

    if company_matches(job, f["company_exclude"]):
        return "company_excluded"
    priority = company_matches(job, f["company_priority"])
    job["priority"] = priority

    # Priority companies skip only the stack-keyword minimum and the per-run cap.
    if not any(k in title for k in f["title_include"]):
        return "title_no_match"
    if title_excluded(title, f["title_exclude"]):
        return "title_excluded"

    if f["require_remote"]:
        remote = bool(job["remote_flag"]) or "remote" in loc or "remote" in title
        if not remote and not loc:
            remote = "remote" in job["description"][:1500].lower()
        if not remote:
            return "not_remote"

    excluded = any(term_in(loc, t) for t in f["location_exclude_terms"])
    allowed = any(term_in(loc, t) for t in f["location_allow_terms"])
    if excluded and not allowed:
        return "location_excluded"

    if job["posted"] and now - job["posted"] > timedelta(days=f["max_age_days"]):
        return "too_old"

    text = f"{title}\n{job['description']}".lower()
    job["stack_hits"] = sum(1 for p in patterns if p.search(text))
    if not priority and job["stack_hits"] < f["min_stack_hits"]:
        return "stack_mismatch"
    return None


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ignore-seen", action="store_true", help="do not skip jobs already evaluated")
    ap.add_argument("--no-boards", action="store_true",
                    help="skip the aggregator boards; only poll the companies listed in config.json")
    args = ap.parse_args()

    cfg = load_config()
    f, limits = cfg["filters"], cfg["limits"]
    patterns = compile_keywords(f["stack_keywords"])
    seen = {} if args.ignore_seen else load_seen()
    now = datetime.now(timezone.utc)

    # Remove stale outputs so a failed run can never be mistaken for a fresh one.
    for name in ("candidates.json", "results.json", "run_status.json"):
        (ROOT / name).unlink(missing_ok=True)

    dropped = Counter()
    errors = []
    candidates = []
    fetched = companies_total = companies_ok = 0

    plan = []  # (source name, [slugs], fetcher)
    for source, slugs in cfg["companies"].items():
        fetcher = FETCHERS.get(source)
        if not fetcher:
            errors.append(f"unknown source '{source}' in config.json (use greenhouse, lever, lever_eu, ashby, recruitee, workable, personio)")
            continue
        unique = {}
        for name in slugs:  # drop duplicate names that differ only by case; the first spelling wins
            if name.strip():
                unique.setdefault(name.strip().lower(), name.strip())
        plan.append((source, list(unique.values()), fetcher))
    for name, enabled in cfg.get("boards", {}).items():
        if not enabled or args.no_boards:
            continue
        board_fn = BOARD_FETCHERS.get(name)
        if not board_fn:
            errors.append(f"unknown board '{name}' in config.json (use remotive, remoteok, arbeitnow)")
            continue
        plan.append((name, [name], lambda _slug, fn=board_fn: fn()))

    dupes = set()
    for source, slugs, fetcher in plan:
        for slug in slugs:
            slug = slug.strip()
            if not slug:
                continue
            companies_total += 1
            try:
                jobs = fetcher(slug)
            except Exception as exc:
                errors.append(f"{source}/{slug}: {exc}")
                continue
            if jobs is None:
                errors.append(f"{source}/{slug}: board not found (404) - check the slug")
                continue
            companies_ok += 1
            fetched += len(jobs)
            for job in jobs:
                job["source"] = source
                job.setdefault("company", pretty_company(slug))
                ident = job["job_id"] or job["url"]
                job["uid"] = f"{source}:{slug}:{ident}"
                if not job["url"]:
                    dropped["no_url"] += 1
                    continue
                if job["uid"] in seen:
                    dropped["already_seen"] += 1
                    continue
                reason = reject_reason(job, f, patterns, now)
                if reason:
                    dropped[reason] += 1
                    continue
                dupkey = (job["company"].lower(), job["title"].lower())
                if dupkey in dupes:
                    dropped["duplicate"] += 1
                    continue
                dupes.add(dupkey)
                candidates.append(job)
            time.sleep(0.3)

    # Priority companies first (never cut by the cap), then best stack overlap, then newest.
    def rank(j):
        return (-j["stack_hits"], -(j["posted"].timestamp() if j["posted"] else 0))
    prio = sorted((j for j in candidates if j["priority"]), key=rank)
    rest = sorted((j for j in candidates if not j["priority"]), key=rank)
    cap = limits["max_candidates_per_run"]
    overflow = max(0, len(rest) - cap)
    candidates = prio + rest[:cap]

    output = []
    for i, j in enumerate(candidates, start=1):
        output.append({
            "ref": f"J{i}",
            "uid": j["uid"],
            "company": j["company"],
            "title": j["title"],
            "url": j["url"],
            "location": j["location"],
            "posted": j["posted"].date().isoformat() if j["posted"] else "",
            "priority": j["priority"],
            "stack_hits": j["stack_hits"],
            "description": j["description"][: limits["description_max_chars"]],
        })

    save_json("candidates.json", output)
    save_json("run_status.json", {
        "run_at": now.isoformat(timespec="seconds"),
        "companies_total": companies_total,
        "companies_ok": companies_ok,
        "fetched": fetched,
        "passed_filters": len(output),
        "deferred_over_cap": overflow,
        "dropped": dict(dropped),
        "errors": errors,
    })

    print(f"Sources: {companies_ok}/{companies_total} reachable | jobs fetched: {fetched}")
    print(f"Dropped: {dict(dropped) or 'nothing'}")
    print(f"Candidates written to candidates.json: {len(output)}" + (f" (+{overflow} over the cap, will come back tomorrow)" if overflow else ""))
    for err in errors:
        print(f"  ! {err}", file=sys.stderr)

    if companies_total == 0:
        print("No companies or boards configured - edit config.json.", file=sys.stderr)
        sys.exit(2)
    if companies_ok == 0:
        print("Every source failed - check network access and config.json.", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
