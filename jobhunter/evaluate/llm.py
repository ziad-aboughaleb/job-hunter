"""Talking to the language model.

LLMClient.complete(system, user) sends ONE independent request and returns the model's text.
Two kinds of server are supported (config.json -> llm.provider):

    "openai"   any OpenAI-compatible chat API: Gemini, OpenAI, OpenRouter, Groq, LM Studio, llama.cpp...
    "ollama"   a local Ollama server

Errors are sorted by what the caller should do about them:
    LLMUnavailable   server unreachable                     -> stop the run
    LLMFatal         wrong key / unknown model              -> stop the run (every job would fail)
    TruncatedOutput  the answer was cut off at the limit    -> retry with a bigger limit
    LLMError         anything else                          -> skip this job, try the next
"""
import os
from typing import Any, Dict, Optional

from jobhunter.helpers import http
from jobhunter.evaluate.prompt import JSON_HINT, RESULT_SCHEMA


class LLMError(RuntimeError):
    """A problem with one request."""


class LLMUnavailable(LLMError):
    """The server cannot be reached."""


class LLMFatal(LLMError):
    """A problem that will affect every request (bad API key, unknown model)."""


class TruncatedOutput(ValueError):
    """The model ran out of output tokens before finishing its JSON."""


class LLMClient:
    def __init__(self, cfg: Dict[str, Any], model: Optional[str] = None):
        if cfg["provider"] not in ("openai", "ollama"):
            raise ValueError("llm.provider must be 'openai' or 'ollama'")
        self.provider = cfg["provider"]
        self.model = model or cfg["model"]
        self.base_url = cfg["base_url"].rstrip("/")
        self.api_key_env = cfg["api_key_env"]
        self.temperature = cfg["temperature"]
        self.timeout = cfg["timeout"]
        self.num_ctx = cfg["num_ctx"]
        self.extra_body = cfg.get("extra_body") or {}
        self.keep_alive = cfg["keep_alive"]
        # These three can change while the run is in progress (see the fallbacks below):
        self.max_output_tokens = cfg["max_output_tokens"]
        self.json_mode = cfg["json_mode"]
        self.think: Optional[bool] = cfg.get("think")

    # ------------------------------------------------------------------ #
    def complete(self, system: str, user: str) -> str:
        """Send one request and return the model's text reply."""
        try:
            if self.provider == "ollama":
                return self._ollama(system, user)
            return self._openai(system, user)
        except http.NetworkError as exc:
            raise LLMUnavailable(str(exc))
        except http.HttpStatusError as exc:
            raise self._classify(exc)

    def grow_output_budget(self) -> None:
        """Called after a truncated answer: allow longer answers from now on."""
        self.max_output_tokens = min(self.max_output_tokens * 2, 8000)

    @staticmethod
    def _classify(exc: http.HttpStatusError) -> LLMError:
        if exc.code in (401, 403):
            return LLMFatal(f"authentication failed ({exc}). Check your API key.")
        if exc.code == 404:
            return LLMFatal(f"model or endpoint not found ({exc}). Check llm.model and llm.base_url "
                            "(for Ollama: run `ollama pull <model>`).")
        return LLMError(str(exc))

    # ------------------------------------------------------------------ #
    def _openai(self, system: str, user: str) -> str:
        key = os.environ.get(self.api_key_env, "")
        if not key:
            raise LLMFatal(f"{self.api_key_env} is not set. Put it in .env (see examples/.env.example).")
        url = self.base_url + "/chat/completions"
        headers = {"Authorization": f"Bearer {key}"}

        def build() -> Dict[str, Any]:
            if self.json_mode == "schema":
                response_format = {"type": "json_schema",
                                   "json_schema": {"name": "job_evaluation", "schema": RESULT_SCHEMA}}
            else:
                response_format = {"type": "json_object"}
            payload = {
                "model": self.model,
                "messages": [{"role": "system", "content": system + JSON_HINT},
                             {"role": "user", "content": user}],
                "temperature": self.temperature,
                "max_tokens": self.max_output_tokens,
                "response_format": response_format,
            }
            payload.update(self.extra_body)
            return payload

        try:
            data = http.post_json(url, build(), headers=headers, timeout=self.timeout)
        except http.HttpStatusError as exc:
            # Some providers reject strict JSON schemas. Fall back to plain JSON mode, once, for the rest of the run.
            if exc.code == 400 and self.json_mode == "schema":
                self.json_mode = "object"
                data = http.post_json(url, build(), headers=headers, timeout=self.timeout)
            else:
                raise
        choice = data["choices"][0]
        if choice.get("finish_reason") == "length":
            raise TruncatedOutput("output cut off at the token limit")
        return (choice.get("message") or {}).get("content") or ""

    def _ollama(self, system: str, user: str) -> str:
        url = self.base_url + "/api/chat"
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": False,
            "format": RESULT_SCHEMA,
            "keep_alive": self.keep_alive,
            "options": {"temperature": self.temperature, "num_ctx": self.num_ctx,
                        "num_predict": self.max_output_tokens},
        }
        if self.think is not None:
            payload["think"] = self.think
        try:
            data = http.post_json(url, payload, timeout=self.timeout)
        except http.HttpStatusError as exc:
            # Models without a "thinking" mode reject the option. Drop it, once, for the rest of the run.
            if exc.code == 400 and "think" in exc.body.lower() and "think" in payload:
                self.think = None
                payload.pop("think")
                data = http.post_json(url, payload, timeout=self.timeout)
            else:
                raise
        if data.get("done_reason") == "length":
            raise TruncatedOutput("output cut off at the token limit")
        return data["message"]["content"]
