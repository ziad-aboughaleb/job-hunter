from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

import httpx

from jobhunter.core.settings import settings
from jobhunter.models import Job

DEFINITIVE_INVALID_STATUS = {404, 410}


class SlugStatus(Enum):
  VALID = "valid"
  INVALID = "invalid"
  UNKNOWN = "unknown"


class BaseSource(ABC):
  name: str
  domains: list[str]
  is_subdomain: bool = False
  is_aggregator: bool = False
  board_config: dict[str, Any] | bool
  enabled: bool

  def __init__(self):
    super().__init__()
    self.board_config = settings.boards.get(self.name, {})
    if isinstance(self.board_config, dict):
      self.enabled = self.board_config.get("enabled", True)
    else:
      self.enabled = bool(self.board_config)

  def validate_slug(self, slug: str) -> SlugStatus:
    """Validates a slug and returns its status."""
    try:
      self.fetch(slug=slug)
      return SlugStatus.VALID

    except httpx.HTTPStatusError as e:
      if e.response.status_code in DEFINITIVE_INVALID_STATUS:
        return SlugStatus.INVALID
      return SlugStatus.UNKNOWN

    except Exception:
      return SlugStatus.UNKNOWN

  @abstractmethod
  def fetch(self, slug: str = "", **kwargs) -> list[Job]:
    pass
