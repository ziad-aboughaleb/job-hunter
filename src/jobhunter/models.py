from pydantic import BaseModel, Field

from jobhunter.core.settings import settings


class Job(BaseModel):
  source: str
  board: str
  company: str
  job_id: str
  title: str
  url: str
  location: str
  remote: bool | None = None
  posted: str = ""
  description: str


class Candidate(BaseModel):
  ref: str = Field(..., description="Short reference ID (e.g., J1, J2)")
  uid: str = Field(..., description="Unique compound identifier: source:board:job_id_or_url")
  priority: bool = False
  stack_hits: int = 0
  status: str = Field(default="pending", description="Pipeline status: pending, saved, applied, rejected")
  source: str = ""
  board: str = ""
  company: str
  job_id: str = ""
  title: str
  url: str
  location: str
  remote: bool | None = None
  posted: str = ""
  description: str = ""

  @classmethod
  def from_job(cls, job: Job, ref: str, priority: bool, stack_hits: int) -> Candidate:
    """Factory method to convert a raw scraped Job into a stored Candidate."""
    uid = f"{job.source}:{job.board}:{job.job_id or job.url}"

    max_chars = settings.limits.description_max_chars
    truncated_description = (job.description or "")[:max_chars]

    return cls(
      ref=ref,
      uid=uid,
      priority=priority,
      stack_hits=stack_hits,
      status="pending",
      source=job.source,
      board=job.board,
      company=job.company,
      job_id=job.job_id,
      title=job.title,
      url=job.url,
      location=job.location,
      remote=job.remote,
      posted=job.posted,
      description=truncated_description,
    )


class AIResult(BaseModel):
  job_id: str
  score: int
  hard_fail: bool
  strengths: list[str]
  gaps: list[str]
  pitch: str
