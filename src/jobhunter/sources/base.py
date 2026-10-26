from abc import ABC, abstractmethod

from jobhunter.models import Job


class BaseSource(ABC):
  name: str
  domains: list[str]
  is_aggregator: bool = False

  @abstractmethod
  def fetch(self, slug: str = "", **kwargs) -> list[Job]:
    pass
