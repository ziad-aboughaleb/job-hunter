import atexit
import time

import httpx

RETRYABLE_STATUS = {408, 429}

CLIENT = httpx.Client(headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})

atexit.register(CLIENT.close)


def _should_retry(e: httpx.HTTPError) -> bool:
  if isinstance(e, httpx.HTTPStatusError):
    code = e.response.status_code
    return code in RETRYABLE_STATUS or code >= 500
  return isinstance(e, httpx.RequestError)


def fetch_json(
  url: str, headers: dict | None = None, timeout: float = 15.0, retries: int = 3, backoff: float = 1.5, expected_type: type | None = None, **kwargs
) -> list | dict:
  """Fetches JSON data from a given URL with optional headers, timeout, retries, and backoff."""
  if retries <= 0:
    raise ValueError("retries must be at least 1")

  last_error: Exception | None = None

  for attempt in range(retries):
    try:
      response = CLIENT.get(url, headers=headers, timeout=timeout, **kwargs)
      response.raise_for_status()
      data = response.json()

      if expected_type and not isinstance(data, expected_type):
        raise ValueError(f"Expected {expected_type.__name__} from {url}, got {type(data).__name__}")

      return data

    except httpx.HTTPError as e:
      last_error = e
      if not _should_retry(e):
        raise

      if attempt < retries - 1:
        time.sleep(backoff * (2**attempt))

    except ValueError as e:
      raise RuntimeError(f"JSON decoding error for {url}: {e}") from e

  raise last_error if last_error else RuntimeError(f"Failed to fetch JSON from {url} after {retries} attempts.")


def fetch_url(url: str, headers: dict | None = None, timeout: float = 15.0, retries: int = 3, backoff: float = 1.5, **kwargs) -> httpx.Response:
  """Fetches raw content from a given URL with optional headers, timeout, retries, and backoff."""
  if retries <= 0:
    raise ValueError("retries must be at least 1")

  last_error: Exception | None = None

  for attempt in range(retries):
    try:
      response = CLIENT.get(url, headers=headers, timeout=timeout, **kwargs)
      response.raise_for_status()
      return response

    except httpx.HTTPError as e:
      last_error = e
      if not _should_retry(e):
        raise

      if attempt < retries - 1:
        time.sleep(backoff * (2**attempt))

  raise last_error if last_error else RuntimeError(f"Failed to fetch URL {url} after {retries} attempts.")
