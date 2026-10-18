"""Tiny HTTP helpers on top of urllib. No third-party packages needed.

Two kinds of failure are told apart, because callers react differently:
    NetworkError     the server could not be reached (DNS, refused connection, timeout)
    HttpStatusError  the server answered with an error status (401, 400, 500, ...)
A 404 on a GET is not an error: it means "that company/board does not exist" and returns None.
"""
import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

USER_AGENT = "Mozilla/5.0 (compatible; job-hunter/3.0)"
RETRY_STATUSES = (429, 500, 502, 503, 504)  # temporary problems worth retrying


class NetworkError(Exception):
    """The server could not be reached."""


class HttpStatusError(Exception):
    """The server replied with an error status."""

    def __init__(self, code: int, body: str):
        super().__init__(f"HTTP {code}: {body[:300]}")
        self.code = code
        self.body = body


def _retry_wait(error: urllib.error.HTTPError, body: str, attempt: int) -> float:
    """Seconds to wait before retrying: honour Retry-After (header, or Telegram's JSON field), else back off."""
    header = error.headers.get("Retry-After") if error.headers else None
    try:
        return min(float(header), 90)
    except (TypeError, ValueError):
        pass
    try:
        return min(float(json.loads(body)["parameters"]["retry_after"]), 90)
    except (ValueError, KeyError, TypeError):
        return min(3 * 2 ** attempt, 90)


def _read(request: urllib.request.Request, timeout: float) -> str:
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", "replace")


def _send_with_retries(request: urllib.request.Request, timeout: float, retries: int,
                       not_found_is_none: bool) -> Optional[str]:
    last: Exception = NetworkError("no attempt made")
    for attempt in range(retries + 1):
        try:
            return _read(request, timeout)
        except urllib.error.HTTPError as exc:  # must come before URLError: HTTPError is a subclass of it
            body = exc.read().decode("utf-8", "replace")
            if exc.code == 404 and not_found_is_none:
                return None
            last = HttpStatusError(exc.code, body)
            if exc.code not in RETRY_STATUSES:
                raise last
            wait = _retry_wait(exc, body, attempt)
        except (urllib.error.URLError, OSError) as exc:  # includes timeouts
            last = NetworkError(str(getattr(exc, "reason", exc)))
            wait = 1.5 * (attempt + 1)
        if attempt < retries:
            time.sleep(wait)
    raise last


def get_text(url: str, accept: str = "*/*", retries: int = 2, timeout: float = 25) -> Optional[str]:
    """GET a URL. Returns None on 404. Retries temporary failures, then raises."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    return _send_with_retries(request, timeout, retries, not_found_is_none=True)


def get_json(url: str, **kwargs: Any) -> Optional[Any]:
    """GET and parse JSON. Returns None on 404."""
    text = get_text(url, accept="application/json", **kwargs)
    return None if text is None else json.loads(text)


def post_json(url: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None,
              timeout: float = 30, retries: int = 3) -> Any:
    """POST a JSON body and parse the JSON reply. Retries rate limits and server errors."""
    all_headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT, **(headers or {})}
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=all_headers)
    text = _send_with_retries(request, timeout, retries, not_found_is_none=False)
    return json.loads(text)
