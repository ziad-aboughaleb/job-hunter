"""Ashby: https://api.ashbyhq.com/posting-api/job-board/<name>"""
from typing import List, Optional

from jobhunter.helpers import http
from jobhunter.helpers.models import Job
from jobhunter.helpers.textutil import clean_html, parse_date, pretty_company

URL = "https://api.ashbyhq.com/posting-api/job-board/{slug}"


def fetch(slug: str) -> Optional[List[Job]]:
    data = http.get_json(URL.format(slug=slug))
    if data is None:
        return None
    company = pretty_company(slug)
    jobs = []
    for item in data.get("jobs", []):
        if item.get("isListed") is False:  # hidden postings
            continue
        extra = [s.get("location", "") if isinstance(s, dict) else str(s)
                 for s in item.get("secondaryLocations") or []]
        location = ", ".join(x for x in [item.get("location", "")] + extra if x)
        remote = bool(item.get("isRemote")) or str(item.get("workplaceType", "")).lower() == "remote"
        jobs.append(Job(
            source="ashby", board=slug, company=company,
            job_id=str(item.get("id", "")),
            title=item.get("title") or "",
            url=item.get("jobUrl") or item.get("applyUrl") or "",
            location=location,
            remote=True if remote else None,
            posted=parse_date(item.get("publishedAt") or item.get("publishedDate")),
            description=item.get("descriptionPlain") or clean_html(item.get("descriptionHtml")),
        ))
    return jobs
