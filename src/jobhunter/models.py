from pydantic import BaseModel


class Job(BaseModel):
  source: str
  board: str
  company: str
  job_id: str
  title: str
  url: str
  location: str
  remote: bool | None = None
  description: str
  posted: str = ""


class AIResult(BaseModel):
  job_id: str
  score: int
  hard_fail: bool
  strengths: list[str]
  gaps: list[str]
  pitch: str
