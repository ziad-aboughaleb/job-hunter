"""Arbeitnow (aggregator, mostly Europe): https://www.arbeitnow.com/api/job-board-api

Options (config.json -> boards.arbeitnow):
    pages   how many result pages to read, default 2
"""
from typing import List

from jobhunter.helpers import http
from jobhunter.helpers.models import Job
from jobhunter.helpers.textutil import clean_html, parse_date


def fetch(options: dict) -> List[Job]:
    jobs, url = [], "https://www.arbeitnow.com/api/job-board-api"
    for _ in range(int(options.get("pages", 2))):
        data = http.get_json(url)
        if data is None:
            break
        for item in data.get("data", []):
            created = item.get("created_at")  # epoch seconds
            tags = ", ".join(item.get("tags") or [])
            jobs.append(Job(
                source="arbeitnow", board="arbeitnow",
                company=item.get("company_name") or "Unknown",
                job_id=str(item.get("slug", "")),
                title=item.get("title") or "",
                url=item.get("url") or "",
                location=item.get("location") or "",
                remote=True if item.get("remote") else None,
                posted=parse_date(created * 1000) if isinstance(created, (int, float)) else parse_date(created),
                description=(f"Tags: {tags}\n\n" if tags else "") + clean_html(item.get("description")),
            ))
        url = (data.get("links") or {}).get("next")
        if not url:
            break
    return jobs
