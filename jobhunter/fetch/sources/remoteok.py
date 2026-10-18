"""RemoteOK (aggregator): https://remoteok.com/api  (please keep a link back to the site when sharing results)"""
from typing import List

from jobhunter.helpers import http
from jobhunter.helpers.models import Job
from jobhunter.helpers.textutil import clean_html, parse_date


def fetch(options: dict) -> List[Job]:
    data = http.get_json("https://remoteok.com/api")
    jobs = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict) or not item.get("position"):
            continue  # the first element of the feed is a legal notice, not a job
        tags = ", ".join(item.get("tags") or [])
        epoch = item.get("epoch")
        jobs.append(Job(
            source="remoteok", board="remoteok",
            company=item.get("company") or "Unknown",
            job_id=str(item.get("id") or item.get("slug") or ""),
            title=item.get("position") or "",
            url=item.get("url") or item.get("apply_url") or "",
            location=item.get("location") or "Remote",
            remote=True,
            posted=parse_date(item.get("date")) or (parse_date(epoch * 1000) if epoch else None),
            description=(f"Tags: {tags}\n\n" if tags else "") + clean_html(item.get("description")),
        ))
    return jobs
