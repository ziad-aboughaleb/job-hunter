import logging
import re
import xml.etree.ElementTree as ET

import httpx

from jobhunter.core.http import fetch_url
from jobhunter.core.logger import console
from jobhunter.core.textutil import clean_html, parse_date
from jobhunter.models import Job
from jobhunter.sources.base import BaseSource

logger = logging.getLogger(__name__)


class Source(BaseSource):
  name = "personio"
  domains = ["personio.de", "personio.com"]
  url_patterns = [re.compile(r"(?://|https?://)(?!www\.)(?P<slug>[a-zA-Z0-9-]+)\.(?:jobs\.)?personio\.(?:de|com|es|fr|it)")]

  def fetch(self, slug: str = "", **kwargs) -> list[Job]:
    """Fetches job listings from a specific company's Personio XML feed."""
    if not slug:
      raise ValueError(f"A company slug must be provided to fetch {self.name} jobs.")

    response = None
    base_url = ""
    headers = {"Accept": "application/xml,text/xml,*/*"}
    last_error = None

    for domain in ("de", "com"):
      base_url = f"https://{slug}.jobs.personio.{domain}"
      url = f"{base_url}/xml?language=en"

      try:
        response = fetch_url(url, headers=headers)
        break
      except httpx.HTTPStatusError as e:
        last_error = e
        if e.response.status_code == 404:
          continue
        raise
      except httpx.RequestError as e:
        last_error = e
        continue

    if not response:
      if last_error:
        raise last_error
      return []

    try:
      root = ET.fromstring(response.text)
    except ET.ParseError as exc:
      logger.error(f"[ {self.name} ] Failed to parse XML for '{slug}': {exc}")
      console.print(f"  [red]✖ [ {self.name} ] Failed to parse XML for '{slug}'[/red]")
      return []

    jobs: list[Job] = []

    for position in root.iter("position"):

      def field(tag: str, pos=position) -> str:
        return (pos.findtext(tag) or "").strip()

      job_id = str(field("id") or "")
      title = str(field("name") or "")
      job_url = str(f"{base_url}/job/{job_id}" if job_id else "")

      if not all([job_id, title, job_url]):
        logger.warning(f"[ {self.name} ] Skipping item with missing required fields: {position.attrib}")
        console.print(f"  [yellow]⚠ [ {self.name} ] Skipping item with missing required fields.[/yellow]")
        continue

      try:
        offices = [field("office")] + [(o.text or "").strip() for o in position.findall("additionalOffices/office")]
        location = ", ".join(dict.fromkeys(o for o in offices if o))

        sections = []
        for block in position.findall("jobDescriptions/jobDescription"):
          name = (block.findtext("name") or "").strip()
          value = clean_html(block.findtext("value"))
          if value:
            sections.append(f"{name}\n{value}" if name else value)

        facts = [
          f"{label}: {field(tag)}"
          for label, tag in (
            ("Seniority", "seniority"),
            ("Years of experience", "yearsOfExperience"),
            ("Employment", "employmentType"),
            ("Schedule", "schedule"),
          )
          if field(tag)
        ]

        description = ("\n".join(facts) + "\n\n" if facts else "") + "\n\n".join(sections)

        jobs.append(
          Job(
            source=self.name,
            board=slug,
            company=field("subcompany") or slug.replace("-", " ").title(),
            job_id=job_id,
            title=title,
            url=job_url,
            location=location,
            remote=None,
            posted=parse_date(field("createdAt")),
            description=description,
          )
        )

      except Exception as e:
        logger.exception(f"[ {self.name} ] Error parsing job '{job_id}' for '{slug}': {e}")
        console.print(f"  [red]✖ [ {self.name} ] Error parsing job '{job_id}'[/red]")
        continue

    return jobs
