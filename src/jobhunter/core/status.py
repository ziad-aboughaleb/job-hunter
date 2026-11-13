from datetime import UTC, datetime
from typing import Literal

from jobhunter.core.paths import DATA_PATH, read, write
from jobhunter.models import RunStatus

STATUS_FILE = DATA_PATH / "runstatus.json"


def start_stage(stage: Literal["fetch", "evaluate", "send"], reset: bool = False) -> RunStatus:
  raw = {} if reset else read(STATUS_FILE, dict)
  status = RunStatus(**raw) if raw and raw.get("status") == "running" else RunStatus()
  status.set_stage(stage)
  write(STATUS_FILE, status.model_dump(mode="json"))
  return status


def save_status(status: RunStatus) -> None:
  status.updated_at = datetime.now(UTC)
  write(STATUS_FILE, status.model_dump(mode="json"))
