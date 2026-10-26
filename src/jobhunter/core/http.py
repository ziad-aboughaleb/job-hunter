import time
from typing import Any

import httpx


def fetch_json(
  url: str, headers: dict | None = None, timeout: float = 15.0, retries: int = 3, backoff: float = 1.5, expected_type: type | None = None, **kwargs
) -> Any | None:
  """Fetches JSON data from a given URL with optional headers, timeout, retries, and backoff."""
  req_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

  if headers:
    req_headers.update(headers)

  for attempt in range(retries):
    try:
      response = httpx.get(url, headers=req_headers, timeout=timeout, http2=True, **kwargs)
      response.raise_for_status()

      data = response.json()

      if expected_type and not isinstance(data, expected_type):
        print(f"Warning: Expected {expected_type.__name__} from {url}, got {type(data).__name__}")
        return None

      return data

    except httpx.HTTPError as e:
      if attempt == retries - 1:
        print(f"HTTP Error fetching {url}: {e}")
        return None
      time.sleep(backoff)

    except ValueError as e:
      print(f"JSON Decode Error from {url}: {e}")
      return None

  return None


def fetch_url(url: str, headers: dict | None = None, timeout: float = 15.0, retries: int = 3, backoff: float = 1.5, **kwargs) -> httpx.Response | None:
  """Fetches raw content from a given URL with optional headers, timeout, retries, and backoff."""
  req_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

  if headers:
    req_headers.update(headers)

  for attempt in range(retries):
    try:
      response = httpx.get(url, headers=req_headers, timeout=timeout, http2=True, **kwargs)
      response.raise_for_status()
      return response
    except httpx.HTTPError as e:
      if attempt == retries - 1:
        print(f"HTTP Error fetching {url}: {e}")
        return None
      time.sleep(backoff)

  return None
