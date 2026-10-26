from abc import ABC, abstractmethod
from typing import Any

from jobhunter.core.settings import settings
from jobhunter.models import Job


class BaseSource(ABC):
  name: str
  domains: list[str]
  is_aggregator: bool = False
  board_config: dict[str, Any] | bool
  enabled: bool

  def __init__(self):
    super().__init__()
    board_config = settings.boards.get(self.name, {})
    if isinstance(board_config, dict):
      self.enabled = board_config.get("enabled", True)
    else:
      self.enabled = bool(board_config)

  @abstractmethod
  def fetch(self, slug: str = "", **kwargs) -> list[Job]:
    pass
