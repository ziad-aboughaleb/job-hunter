"""Lever: https://api.lever.co/v0/postings/<name>?mode=json  (EU accounts use api.eu.lever.co)"""
from typing import List, Optional

from jobhunter.helpers import http
from jobhunter.helpers.models import Job
from jobhunter.helpers.textutil import clean_html, parse_date, pretty_company


def fetch(slug: str, eu: bool = False) -> Optional[List[Job]]:
    host = "api.eu.lever.co" if eu else "api.lever.co"
    data = http.get_json(f"https://{host}/v0/postings/{slug}?mode=json")
    if data is None:
        return None
    company = pretty_company(slug)
    jobs = []
    for item in data if isinstance(data, list) else []:
        categories = item.get("categories") or {}
        location = categories.get("location") or ", ".join(categories.get("allLocations") or [])
        parts = [item.get("descriptionPlain", "")]
        for block in item.get("lists") or []:  # "Requirements", "Responsibilities", ...
            parts.append(f"{block.get('text', '')}\n{clean_html(block.get('content'))}")
        parts.append(item.get("additionalPlain", ""))
        jobs.append(Job(
            source="lever_eu" if eu else "lever", board=slug, company=company,
            job_id=str(item.get("id", "")),
            title=item.get("text") or "",
            url=item.get("hostedUrl") or "",
            location=location or "",
            remote=True if str(item.get("workplaceType", "")).lower() == "remote" else None,
            posted=parse_date(item.get("createdAt")),
            description="\n\n".join(p for p in parts if p).strip(),
        ))
    return jobs


def fetch_eu(slug: str) -> Optional[List[Job]]:
    return fetch(slug, eu=True)
