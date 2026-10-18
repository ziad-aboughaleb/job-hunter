"""Greenhouse: https://boards-api.greenhouse.io/v1/boards/<name>/jobs?content=true"""
from typing import List, Optional

from jobhunter.helpers import http
from jobhunter.helpers.models import Job
from jobhunter.helpers.textutil import clean_html, parse_date, pretty_company

URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"


def fetch(slug: str) -> Optional[List[Job]]:
    data = http.get_json(URL.format(slug=slug))
    if data is None:
        return None
    company = pretty_company(slug)
    return [
        Job(
            source="greenhouse", board=slug, company=company,
            job_id=str(item.get("id", "")),
            title=item.get("title") or "",
            url=item.get("absolute_url") or "",
            location=(item.get("location") or {}).get("name") or "",
            posted=parse_date(item.get("first_published") or item.get("updated_at")),
            description=clean_html(item.get("content")),
        )
        for item in data.get("jobs", [])
    ]
