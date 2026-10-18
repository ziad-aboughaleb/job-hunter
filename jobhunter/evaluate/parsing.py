"""Turning the model's reply into a clean result.

Models make small mistakes: they wrap JSON in code fences, add chatty text, write "77%" instead of 77, or return
a lone string where a list was asked for. parse_json_text() and normalize() repair what is safe to repair, and raise
ValueError for what is not, so the caller can ask the model again.
"""
import json
import re
from typing import Any, Dict, Optional


def parse_json_text(text: Optional[str]) -> Any:
    """Parse the model's reply. Tolerates ```json fences and chatty text around the object."""
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    if not text.startswith("{") and "{" in text and "}" in text:
        text = text[text.index("{"): text.rindex("}") + 1]
    return json.loads(text)


def _as_list(value: Any) -> list:
    if isinstance(value, str):  # a lone string must not be split into characters
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(x).strip() for x in value if str(x).strip()][:3]


def normalize(raw: Any, ref: str) -> Dict[str, Any]:
    """Turn the model's JSON into a clean result. Raises ValueError if it is unusable (the caller retries)."""
    if not isinstance(raw, dict):
        raise ValueError("model output is not a JSON object")
    if "score" not in raw:  # never silently treat a missing score as 0
        raise ValueError("missing 'score'")
    score = int(round(float(str(raw["score"]).replace("%", "").strip())))
    hard_fail = str(raw.get("hard_fail") or "").strip()
    result = {
        "ref": ref,
        "score": max(0, min(100, score)),
        "hard_fail": hard_fail or None,
        "strengths": _as_list(raw.get("strengths")),
        "gaps": _as_list(raw.get("gaps")),
        "pitch": str(raw.get("pitch") or "").strip(),
    }
    if result["hard_fail"]:  # a hard fail always means score 0 and nothing else
        result.update(score=0, strengths=[], gaps=[], pitch="")
    return result
