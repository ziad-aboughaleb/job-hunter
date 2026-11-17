import json
import os
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.aliases import AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict

from .paths import CONFIG_PATH, read


class StrictModel(BaseModel):
  model_config = ConfigDict(extra="forbid")


class ProfileConfig(StrictModel):
  target_roles: str = ""


class FiltersConfig(StrictModel):
  title_include: list[str] = []
  title_exclude: list[str] = []
  stack_keywords: list[str] = []
  min_stack_hits: int = 0
  company_exclude: list[str] = []
  company_priority: list[str] = []
  require_remote: bool = True
  remote_keywords: list[str] = ["remote", "wfh", "work from home", "anywhere", "telecommute", "fully remote", "100% remote"]
  location_exclude_terms: list[str] = ["us only", "us-only", "united states only", "canada only", "uk only", "must reside in"]
  location_allow_terms: list[str] = ["worldwide", "emea", "anywhere", "global"]
  location_require_terms: list[str] = []
  max_age_days: int = 14


class LimitsConfig(StrictModel):
  max_candidates_per_run: int = 30
  description_max_chars: int = 7000
  seen_retention_days: int = 90
  fetch_timeout: int = Field(default=60, ge=1)


class ScoringWeight(StrictModel):
  name: str
  weight: int = Field(ge=1, le=100)
  what: str


class EvaluatingConfig(StrictModel):
  score_threshold: int = Field(default=65, ge=25, le=89)
  low_band: int = 45
  scoring_weights: list[ScoringWeight] = Field(default_factory=list)

  @model_validator(mode="after")
  def calculate_low_band(self) -> EvaluatingConfig:
    if self.scoring_weights and sum(w.weight for w in self.scoring_weights) != 100:
      raise ValueError("scoring_weights must sum to 100")
    self.low_band = max(0, self.score_threshold - 20)
    return self


class LLMConfig(StrictModel):
  base_url: str | None = None
  model: str | None = None
  request_delay: int = 5
  temperature: float = 0.0
  timeout: int = 600


class TelegramConfig(StrictModel):
  link_preview: bool = False
  notify_on_empty: bool = True
  send_low_scores: bool = False
  message_delay: float = Field(default=1.0, ge=0.0)


class WorkersConfig(StrictModel):
  fetch_workers: int = Field(default=8, ge=1, le=20)
  evaluation_workers: int = Field(default=1, ge=1, le=20)
  discovery_workers: int = Field(default=8, ge=1, le=10)
  pruning_workers: int = Field(default=8, ge=1, le=20)


class Settings(BaseSettings):
  telegram_bot_token: str = Field(default="", validation_alias=AliasChoices("TELEGRAM_BOT_TOKEN", "telegram_bot_token"))
  telegram_chat_id: str = Field(default="", validation_alias=AliasChoices("TELEGRAM_CHAT_ID", "telegram_chat_id"))
  llm_api_key: str = Field(default="", validation_alias=AliasChoices("LLM_API_KEY", "llm_api_key"))

  profile: ProfileConfig = Field(default_factory=ProfileConfig)
  boards: dict[str, Any] = Field(default_factory=dict)
  companies: dict[str, list[str]] = Field(default_factory=dict)
  filters: FiltersConfig = Field(default_factory=FiltersConfig)
  evaluating: EvaluatingConfig = Field(default_factory=EvaluatingConfig)
  llm: LLMConfig = Field(default_factory=LLMConfig)
  telegram: TelegramConfig = Field(default_factory=TelegramConfig)
  limits: LimitsConfig = Field(default_factory=LimitsConfig)
  workers: WorkersConfig = Field(default_factory=WorkersConfig)

  cv_text: str = ""
  preferences_text: str = ""

  model_config = SettingsConfigDict(env_file=".env", extra="ignore")


def load_settings() -> Settings:
  """Loads settings from files or environment variable fallbacks, returning a Settings object."""
  config_path = CONFIG_PATH / "config.json"

  if config_path.exists():
    config_data = read(config_path, dict)
  else:
    config_str = (os.getenv("CONFIG_JSON") or "").strip()
    if not config_str:
      config_data = {}
    else:
      try:
        config_data = json.loads(config_str)
      except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in CONFIG_JSON environment variable: {e}") from e
      if not isinstance(config_data, dict):
        raise ValueError("CONFIG_JSON must be a JSON object")

  # Remove "_help"
  config_data.pop("_help", None)

  # Load Markdown with env fallbacks
  cv_path = CONFIG_PATH / "cv.md"
  cv_text = read(cv_path) if cv_path.exists() else os.getenv("CV") or ""

  pref_path = CONFIG_PATH / "preferences.md"
  preferences_text = read(pref_path) if pref_path.exists() else os.getenv("PREFERENCES") or ""

  return Settings(
    cv_text=cv_text,
    preferences_text=preferences_text,
    **config_data,
  )


settings = load_settings()
