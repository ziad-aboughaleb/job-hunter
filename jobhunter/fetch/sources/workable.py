"""Workable: https://apply.workable.com/api/v1/widget/accounts/<name>?details=true"""
from typing import List, Optional

from jobhunter.helpers import http
from jobhunter.helpers.models import Job
from jobhunter.helpers.textutil import clean_html, parse_date, pretty_company

URL = "https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true"


def _location(item: dict, location_obj: dict) -> str:
    parts = [item.get("city") or location_obj.get("city"),
             item.get("state") or location_obj.get("region"),
             item.get("country") or location_obj.get("country")]
    text = ", ".join(p for p in parts if p)
    if text:
        return text
    names = []  # fall back to the list of locations
    for entry in item.get("locations") or []:
        if isinstance(entry, dict):
            names.append(", ".join(x for x in (entry.get("city"), entry.get("region"), entry.get("country")) if x))
    return " / ".join(n for n in names if n)


def fetch(slug: str) -> Optional[List[Job]]:
    data = http.get_json(URL.format(slug=slug))
    if not isinstance(data, dict):
        return None
    company = data.get("name") or pretty_company(slug)
    jobs = []
    for item in data.get("jobs", []):
        location_obj = item.get("location") if isinstance(item.get("location"), dict) else {}
        remote = bool(item.get("telecommuting")) or bool(location_obj.get("telecommuting"))
        jobs.append(Job(
            source="workable", board=slug, company=company,
            job_id=str(item.get("shortcode") or item.get("id") or item.get("code") or ""),
            title=item.get("title") or "",
            url=item.get("url") or item.get("shortlink") or item.get("application_url") or "",
            location=_location(item, location_obj),
            remote=True if remote else None,
            posted=parse_date(item.get("published_on") or item.get("created_at")),
            description=clean_html(item.get("description") or item.get("full_description")),
        ))
    return jobs
