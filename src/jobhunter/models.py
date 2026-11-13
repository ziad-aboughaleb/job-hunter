import os
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, computed_field


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
    return cls(
      uid=job.uid,
      priority=priority,
      stack_hits=stack_hits,
      source=job.source,
      board=job.board,
      company=job.company,
      job_id=job.job_id,
      title=job.title,
      url=job.url,
      location=job.location,
      remote=job.remote,
      posted=job.posted,
      description=job.description,
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


class CompactEvaluation(BaseModel):
  """A stripped-down evaluation used only for the history log."""

  hard_fail: bool
  hard_fail_reason: str
  gaps: list[str]
  score: int


class HistoryEntry(BaseModel):
  """Compact audit record of an evaluated candidate (excludes description and verbose LLM text)."""

  recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
  passed: bool
  priority: bool = False
  stack_hits: int = 0
  company: str
  title: str
  url: str
  location: str
  posted: str = ""
  evaluation: CompactEvaluation

  @classmethod
  def from_evaluated(cls, candidate: EvaluatedCandidate, passed: bool) -> HistoryEntry:
    """Factory method to strip out verbose and redundant data."""
    compact_eval = CompactEvaluation(hard_fail=candidate.evaluation.hard_fail, hard_fail_reason=candidate.evaluation.hard_fail_reason, gaps=candidate.evaluation.gaps, score=candidate.evaluation.score)

    return cls(
      passed=passed,
      priority=candidate.priority,
      stack_hits=candidate.stack_hits,
      company=candidate.company,
      title=candidate.title,
      url=candidate.url,
      location=candidate.location,
      posted=candidate.posted,
      evaluation=compact_eval,
    )


class StageMetrics(BaseModel):
  # Fetch
  fetched_total: int = 0
  filtered_passed: int = 0
  skipped_seen: int = 0
  skipped_dupes: int = 0
  skipped_filters: int = 0
  cut_over_cap: int = 0
  new_candidates: int = 0

  # Evaluate
  evaluated_count: int = 0
  eval_passed: int = 0
  hard_failed: int = 0
  low_score: int = 0
  eval_errors: int = 0

  # Send
  sent_count: int = 0
  send_failed: int = 0


class RunStatus(BaseModel):
  """Tracks pipeline state across fetch, evaluate, and send."""

  pid: int = Field(default_factory=os.getpid)
  status: Literal["running", "completed", "failed"] = "running"
  current_stage: Literal["fetch", "evaluate", "send", "done"] = "fetch"
  started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
  updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
  finished_at: datetime | None = None
  metrics: StageMetrics = Field(default_factory=StageMetrics)
  error: str | None = None

  def set_stage(self, stage: Literal["fetch", "evaluate", "send"]) -> None:
    self.current_stage = stage
    self.updated_at = datetime.now(UTC)

  def mark_completed(self) -> None:
    now = datetime.now(UTC)
    self.status = "completed"
    self.current_stage = "done"
    self.updated_at = now
    self.finished_at = now

  def mark_failed(self, error: str) -> None:
    now = datetime.now(UTC)
    self.status = "failed"
    self.error = error
    self.updated_at = now
    self.finished_at = now
