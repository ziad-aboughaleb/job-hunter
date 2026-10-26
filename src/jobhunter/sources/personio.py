import xml.etree.ElementTree as ET

import httpx

from jobhunter.core.textutil import clean_html, parse_date
from jobhunter.models import Job
from jobhunter.sources.base import BaseSource


class Source(BaseSource):
  name = "personio"
  domains = ["personio.de", "personio.com"]
  is_aggregator = False

  def fetch(self, slug: str = "", **kwargs) -> list[Job]:
    """Fetches job listings from a specific company's Personio XML feed."""
    if not slug:
      return []

    text = None
    base_url = ""

    for domain in ("de", "com"):
      base_url = f"https://{slug}.jobs.personio.{domain}"
      url = f"{base_url}/xml?language=en"
      try:
        response = httpx.get(url, headers={"Accept": "application/xml,text/xml,*/*"}, timeout=15.0)
        if response.status_code == 200:
          text = response.text
          break
      except httpx.HTTPError:
        continue

    if not text:
      print(f"Failed to fetch {slug} from Personio (tried .de and .com)")
      return []

    try:
      root = ET.fromstring(text)
    except ET.ParseError as exc:
      print(f"Failed to parse XML for {slug} from Personio: {exc}")
      return []

    jobs = []

    for position in root.iter("position"):

      def field(tag: str, pos=position) -> str:
        return (pos.findtext(tag) or "").strip()

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

      title = field("name")
      job_id = field("id")

      jobs.append(
        Job(
          source=self.name,
          board=slug,
          company=field("subcompany") or slug.replace("-", " ").title(),
          job_id=job_id,
          title=title,
          url=f"{base_url}/job/{job_id}" if job_id else "",
          location=location,
          remote=None,
          posted=parse_date(field("createdAt")),
          description=description,
        )
      )

    return jobs
