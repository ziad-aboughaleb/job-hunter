from typing import Any

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from jobhunter.core.state import load_config

from .paths import get_project_root


class ProfileConfig(BaseModel):
  target_roles: str = ""


class FiltersConfig(BaseModel):
  title_include: list[str] = []
  title_exclude: list[str] = []
  stack_keywords: list[str] = []
  min_stack_hits: int = 0
  company_exclude: list[str] = []
  company_priority: list[str] = []
  require_remote: bool = True
  remote_keywords: list[str] = ["remote", "wfh", "work from home", "anywhere", "telecommute", "fully remote", "100% remote"]
  location_exclude_terms: list[str] = ["us only", "us-only", "united states only", "canada only", "uk only", "must reside in"]
  location_allow_terms: list[str] = []
  location_require_terms: list[str] = []
  max_age_days: int = 14


class LimitsConfig(BaseModel):
  max_candidates_per_run: int = 30
  description_max_chars: int = 7000
  seen_retention_days: int = 90
  fetch_workers: int = 8


class ScoringWeight(BaseModel):
  name: str
  weight: int
  what: str


class LLMConfig(BaseModel):
  provider: str = "openai"
  base_url: str | None = None
  model: str | None = None
  api_key_env: str = "LLM_API_KEY"
  request_delay: int = 5
  temperature: float = 0.0
  timeout: int = 600


class TelegramConfig(BaseModel):
  link_preview: bool = False
  notify_on_empty: bool = True


class Settings(BaseSettings):
  telegram_bot_token: str = ""
  telegram_chat_id: str = ""
  llm_api_key: str = ""

  profile: ProfileConfig = Field(default_factory=ProfileConfig)

  boards: dict[str, Any] = Field(default_factory=dict)
  companies: dict[str, list[str]] = Field(default_factory=dict)

  filters: FiltersConfig = Field(default_factory=FiltersConfig)
  limits: LimitsConfig = Field(default_factory=LimitsConfig)

  score_threshold: int = 75
  scoring_weights: list[ScoringWeight] = Field(default_factory=list)

  llm: LLMConfig = Field(default_factory=LLMConfig)
  telegram: TelegramConfig = Field(default_factory=TelegramConfig)

  cv_text: str = ""
  preferences_text: str = ""

  model_config = SettingsConfigDict(env_file=".env", extra="ignore")


def load_settings() -> Settings:
  """Loads settings from JSON and Markdown files, returning a Settings object."""
  config_dir = get_project_root() / "config"

  # Load JSON
  config_data = load_config()

  # Remove "_help"
  config_data.pop("_help", None)

  # Load Markdown
  cv_path = config_dir / "cv.md"
  pref_path = config_dir / "preferences.md"

  return Settings(
    cv_text=cv_path.read_text(encoding="utf-8") if cv_path.exists() else "",
    preferences_text=pref_path.read_text(encoding="utf-8") if pref_path.exists() else "",
    **config_data,
  )


settings = load_settings()
