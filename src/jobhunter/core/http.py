import atexit
import logging
import time
from typing import Any

import httpx

from jobhunter.core.logger import console

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = {408, 429}
CLIENT = httpx.Client(headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})

atexit.register(CLIENT.close)


def _should_retry(e: httpx.HTTPError) -> bool:
  if isinstance(e, httpx.HTTPStatusError):
    code = e.response.status_code
    return code in RETRYABLE_STATUS or code >= 500
  return isinstance(e, httpx.RequestError)


def fetch_url(url: str, headers: dict | None = None, timeout: float = 15.0, retries: int = 3, backoff: float = 1.5, parse_json: bool = False, expected_type: type | None = None, **kwargs) -> Any:
  """Fetches data from a URL. Returns parsed JSON if `parse_json=True` or `expected_type` is provided, else returns `httpx.Response`."""
  if retries <= 0:
    raise ValueError("retries must be at least 1")

  if expected_type is not None:
    parse_json = True

  for attempt in range(retries):
    try:
      response = CLIENT.get(url, headers=headers, timeout=timeout, **kwargs)
      response.raise_for_status()

      if parse_json:
        data = response.json()
        if expected_type and not isinstance(data, expected_type):
          raise ValueError(f"Expected {expected_type.__name__} from {url}, got {type(data).__name__}")
        return data

      return response

    except httpx.HTTPError as e:
      if _should_retry(e) and attempt < retries - 1:
        time.sleep(backoff * (2**attempt))
      else:
        is_client_not_found = isinstance(e, httpx.HTTPStatusError) and e.response.status_code in {404, 410}
        if not is_client_not_found:
          logger.error(f"HTTP request failed permanently for {url}: {e}")
          console.print(f"  [red]✖ Network error fetching {url}: {e}[/red]")
        raise

    except ValueError as e:
      raise RuntimeError(f"JSON decoding or type error for {url}: {e}") from e
