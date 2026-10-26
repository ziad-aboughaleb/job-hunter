from abc import ABC, abstractmethod
from typing import Any

from jobhunter.core.settings import settings
from jobhunter.models import Job


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

  @abstractmethod
  def fetch(self, slug: str = "", **kwargs) -> list[Job]:
    pass
