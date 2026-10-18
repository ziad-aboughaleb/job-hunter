"""Personio: https://<name>.jobs.personio.de/xml  (or .com). An XML feed with no "remote" flag."""
import xml.etree.ElementTree as ET
from typing import List, Optional

from jobhunter.helpers import http
from jobhunter.helpers.models import Job
from jobhunter.helpers.textutil import clean_html, parse_date, pretty_company

# Personio has no remote flag, so we look for these phrases near the top of the description.
REMOTE_PHRASES = ("fully remote", "100% remote", "remote-first", "remote first",
                  "work from anywhere", "work remotely", "remote position", "remote role")


def looks_remote(location: str, title: str, description: str) -> bool:
    if "remote" in f"{location} {title}".lower():
        return True
    return any(phrase in description[:1500].lower() for phrase in REMOTE_PHRASES)


def fetch(slug: str) -> Optional[List[Job]]:
    text, base = None, ""
    for domain in ("de", "com"):  # a company's feed lives on one of the two domains
        base = f"https://{slug}.jobs.personio.{domain}"
        text = http.get_text(f"{base}/xml?language=en", accept="application/xml,text/xml,*/*")
        if text:
            break
    if not text:
        return None
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError(f"feed is not valid XML ({exc})")

    jobs = []
    for position in root.iter("position"):
        def field(tag: str) -> str:
            return (position.findtext(tag) or "").strip()

        offices = [field("office")] + [(o.text or "").strip() for o in position.findall("additionalOffices/office")]
        location = ", ".join(dict.fromkeys(o for o in offices if o))  # unique, in order

        sections = []
        for block in position.findall("jobDescriptions/jobDescription"):
            name = (block.findtext("name") or "").strip()
            value = clean_html(block.findtext("value"))
            if value:
                sections.append(f"{name}\n{value}" if name else value)
        facts = [f"{label}: {field(tag)}" for label, tag in (
            ("Seniority", "seniority"), ("Years of experience", "yearsOfExperience"),
            ("Employment", "employmentType"), ("Schedule", "schedule")) if field(tag)]
        description = ("\n".join(facts) + "\n\n" if facts else "") + "\n\n".join(sections)

        title, job_id = field("name"), field("id")
        jobs.append(Job(
            source="personio", board=slug,
            company=field("subcompany") or pretty_company(slug),
            job_id=job_id, title=title,
            url=f"{base}/job/{job_id}" if job_id else "",
            location=location,
            remote=True if looks_remote(location, title, description) else None,
            posted=parse_date(field("createdAt")),
            description=description,
        ))
    return jobs
