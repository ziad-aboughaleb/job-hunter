"""Recruitee: https://<name>.recruitee.com/api/offers/"""
from typing import List, Optional

from jobhunter.helpers import http
from jobhunter.helpers.models import Job
from jobhunter.helpers.textutil import clean_html, parse_date, pretty_company

URL = "https://{slug}.recruitee.com/api/offers/"


def fetch(slug: str) -> Optional[List[Job]]:
    data = http.get_json(URL.format(slug=slug))
    if data is None:
        return None
    jobs = []
    for item in data.get("offers", []):
        location = item.get("location") or ", ".join(x for x in (item.get("city"), item.get("country")) if x)
        description = "\n\n".join(x for x in (clean_html(item.get("description")),
                                              clean_html(item.get("requirements"))) if x)
        jobs.append(Job(
            source="recruitee", board=slug,
            company=item.get("company_name") or pretty_company(slug),
            job_id=str(item.get("id") or item.get("guid") or item.get("slug") or ""),
            title=item.get("title") or "",
            url=item.get("careers_url") or item.get("url") or "",
            location=location or "",
            remote=True if item.get("remote") else None,
            posted=parse_date(item.get("published_at") or item.get("created_at")),
            description=description,
        ))
    return jobs
