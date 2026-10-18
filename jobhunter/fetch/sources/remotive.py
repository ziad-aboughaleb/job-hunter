"""Remotive (aggregator): https://remotive.com/api/remote-jobs

Options (config.json -> boards.remotive):
    category   Remotive category, default "software-dev". Other examples: "devops", "data", "design".
    limit      most jobs to request, default 300
Please keep to one run a day; the site asks API users to be gentle.
"""
from typing import List
from urllib.parse import quote

from jobhunter.helpers import http
from jobhunter.helpers.models import Job
from jobhunter.helpers.textutil import clean_html, parse_date


def fetch(options: dict) -> List[Job]:
    url = f"https://remotive.com/api/remote-jobs?limit={int(options.get('limit', 300))}"
    category = options.get("category", "software-dev")
    if category:
        url += f"&category={quote(str(category))}"
    data = http.get_json(url) or {}
    return [
        Job(
            source="remotive", board="remotive",
            company=item.get("company_name") or "Unknown",
            job_id=str(item.get("id", "")),
            title=item.get("title") or "",
            url=item.get("url") or "",
            location=item.get("candidate_required_location") or "Remote",  # e.g. "Worldwide", "USA Only"
            remote=True,
            posted=parse_date(item.get("publication_date")),
            description=clean_html(item.get("description")),
        )
        for item in data.get("jobs", [])
    ]
