from pydantic import BaseModel, Field, computed_field

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

  @computed_field
  @property
  def uid(self) -> str:
    """Dynamically generates a unique identifier for the job."""
    return f"{self.source}:{self.board}:{self.job_id or self.url}"


class Candidate(BaseModel):
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
  def from_job(cls, job: Job, priority: bool, stack_hits: int) -> Candidate:
    """Factory method to convert a raw scraped Job into a stored Candidate."""
    max_chars = settings.limits.description_max_chars
    truncated_description = (job.description or "No description provided.")[:max_chars]

    return cls(
      uid=job.uid,
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


class EvaluationResult(BaseModel):
  """The exact JSON schema the LLM must return."""

  reasoning: str = Field(description="A brief 2-3 sentence thought process analyzing the match before scoring.")
  hard_fail: bool = Field(description="True if the job hits any hard gate or dealbreaker.")
  hard_fail_reason: str = Field(default="", description="If hard_fail is true, a max 12-word explanation. Otherwise empty.")
  strengths: list[str] = Field(description="2-3 short items showing requirements explicitly met by the CV.")
  gaps: list[str] = Field(default_factory=list, description="Missing requirements or weak points compared to the CV.")
  score: int = Field(description="Final match score (0-100) based on the rubric.")
  score_explanation: str = Field(description="A 1-2 sentence explanation of exactly why the job passed or failed the score threshold.")
  pitch: str = Field(default="", description="A short, one-sentence first-person pitch. Empty if score is below threshold.")


class EvaluatedCandidate(Candidate):
  """A candidate that has been evaluated by the AI."""

  evaluation: EvaluationResult
