import logging
import re
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any
from urllib.parse import unquote

import httpx

from jobhunter.core.logger import console
from jobhunter.core.settings import settings
from jobhunter.models import Job

logger = logging.getLogger(__name__)

DEFINITIVE_INVALID_STATUS = {404, 410}


class SlugStatus(Enum):
  VALID = "valid"
  INVALID = "invalid"
  UNKNOWN = "unknown"


class BaseSource(ABC):
  name: str
  domains: list[str]
  url_patterns: list[re.Pattern] = []
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

  def extract_slug(self, url: str) -> str | None:
    """Extracts the company slug from a URL using source-specific regex patterns."""
    if not url:
      return None

    for pattern in self.url_patterns:
      match = pattern.search(url)
      if match:
        slug = match.group("slug").lower().strip()
        slug = unquote(slug)
        if 1 < len(slug) < 60:
          return slug

    return None

  def validate_slug(self, slug: str) -> SlugStatus:
    """Validates a slug and returns its status."""
    if not slug or not isinstance(slug, str):
      return SlugStatus.INVALID

    try:
      self.fetch(slug=slug, skip_parsing=True)
      return SlugStatus.VALID

    except httpx.HTTPStatusError as e:
      if e.response.status_code in DEFINITIVE_INVALID_STATUS:
        return SlugStatus.INVALID
      return SlugStatus.UNKNOWN

    except Exception:
      return SlugStatus.UNKNOWN

  def execute_scraper(self, slug: str = "") -> list[Job]:
    """Executes the scraper for a given source and slug."""
    if not self.enabled:
      return []

    if not self.is_aggregator and not slug:
      logger.warning(f"[ {self.name} ] Skipping execution: Non-aggregator sources require a slug.")
      console.print(f"  [yellow]⚠ [ {self.name} ] Skipping execution: Non-aggregator sources require a slug.[/yellow]")
      return []

    try:
      return self.fetch(slug=slug) or []

    except httpx.HTTPStatusError as e:
      logger.error(f"[ {self.name} ] HTTP {e.response.status_code} error for slug '{slug}': {e}")
      console.print(f"  [red]✖ [ {self.name} ] HTTP {e.response.status_code} error for slug '{slug}'[/red]")
      return []

    except httpx.RequestError as e:
      logger.error(f"[ {self.name} ] Network error while connecting to '{slug}': {e}")
      console.print(f"  [red]✖ [ {self.name} ] Network error while connecting to '{slug}'[/red]")
      return []

    except ValueError as e:
      logger.error(f"[ {self.name} ] Validation error for slug '{slug}': {e}")
      console.print(f"  [red]✖ [ {self.name} ] Validation error for slug '{slug}': {e}[/red]")
      return []

    except Exception as e:
      logger.exception(f"[ {self.name} ] Unexpected error executing scraper for slug '{slug}': {e}")
      console.print(f"  [red]✖ [ {self.name} ] Unexpected error executing scraper for slug '{slug}'[/red]")
      return []

  @abstractmethod
  def fetch(self, slug: str = "", skip_parsing: bool = False, **kwargs) -> list[Job]:
    pass
