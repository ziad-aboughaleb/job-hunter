# Configuration & Settings Guide

`JobHunter` is configured via a combination of environment variables (`.env`), structured configuration (`config/config.json`), and candidate profile/preference documents (`config/cv.md` and `config/preferences.md`).

---

## 🔐 Environment Variables (`.env`)

Secrets and API credentials are managed via Pydantic `BaseSettings` and `.env`. Create a `.env` file in the root directory based on `.env.example`:

```env
# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_telegram_chat_id_here

# LLM API Configuration (OpenAI or compatible endpoint like Ollama/vLLM)
LLM_API_KEY=your_llm_api_key_here
```

---

## ⚙️ Pydantic Settings & `config.json`

The `config/config.json` file controls search targets, filtering rules, scoring weights, concurrency workers, and LLM parameters.

### Sample `config.json`

```json
{
  "profile": {
    "target_roles": "Backend Engineer, Python Developer, Software Engineer"
  },
  "boards": {
    "remotive": {
      "enabled": true,
      "category": "software-dev"
    },
    "remoteok": true
  },
  "companies": {
    "greenhouse": ["stripe", "discord"],
    "lever": ["netflix"]
  },
  "filters": {
    "title_include": ["backend", "python", "engineer"],
    "title_exclude": ["frontend", "react", "manager", "staff"],
    "stack_keywords": [
      "python",
      "fastapi",
      "django",
      "postgresql",
      "docker",
      "aws"
    ],
    "min_stack_hits": 2,
    "company_exclude": ["Crossover", "Turing"],
    "company_priority": ["OpenAI", "Anthropic"],
    "require_remote": true,
    "remote_keywords": [
      "remote",
      "wfh",
      "work from home",
      "anywhere",
      "telecommute",
      "fully remote",
      "100% remote"
    ],
    "location_exclude_terms": [
      "us only",
      "us-only",
      "united states only",
      "canada only",
      "uk only",
      "must reside in"
    ],
    "location_allow_terms": ["worldwide", "emea", "anywhere", "global"],
    "location_require_terms": [],
    "max_age_days": 14
  },
  "limits": {
    "max_candidates_per_run": 30,
    "description_max_chars": 7000,
    "seen_retention_days": 90
  },
  "evaluating": {
    "score_threshold": 65,
    "scoring_weights": [
      {
        "name": "tech_stack_match",
        "weight": 40,
        "what": "How well the job's tech stack matches the candidate's CV."
      },
      {
        "name": "experience_level",
        "weight": 30,
        "what": "Does the required experience match the candidate's years of experience?"
      },
      {
        "name": "role_alignment",
        "weight": 30,
        "what": "Is this a backend-focused engineering role?"
      }
    ]
  },
  "llm": {
    "provider": "openai",
    "base_url": "https://api.openai.com/v1",
    "model": "gpt-4o-mini",
    "request_delay": 5,
    "temperature": 0.0,
    "timeout": 600
  },
  "telegram": {
    "link_preview": false,
    "notify_on_empty": true
  },
  "workers": {
    "fetch_workers": 8,
    "evaluation_workers": 1,
    "discovery_workers": 8,
    "pruning_workers": 8
  }
}
```

### Configuration Sections Breakdown

- **`profile`**: Defines target roles (`target_roles`) used in prompt generation and hard gate evaluation.
- **`boards`**: Toggles aggregator boards (`remotive`, `remoteok`, `arbeitnow`) on or off.
- **`companies`**: Maps ATS source names (`greenhouse`, `lever`, `personio`, `workable`, `recruitee`, `ashby`) to lists of company board slugs.
- **`filters`**:
  - `title_include` / `title_exclude`: Regex word-boundary filters for job titles.
  - `stack_keywords` & `min_stack_hits`: Tech stack keywords that must appear at least `min_stack_hits` times in the job posting.
  - `company_exclude` / `company_priority`: Blacklist companies or elevate VIP companies to priority status.
  - `require_remote` & `remote_keywords`: Ensure remote eligibility.
  - `location_allow_terms`, `location_exclude_terms`, `location_require_terms`: Strict geographic filtering rules.
  - `max_age_days`: Maximum allowable age of job postings (default 14 days).
- **`limits`**:
  - `max_candidates_per_run`: Maximum non-priority candidates evaluated per run.
  - `description_max_chars`: Truncation limit for job descriptions (default 7,000 chars).
  - `seen_retention_days`: Rolling retention period for `seen.json` (default 90 days).
- **`evaluating`**:
  - `score_threshold`: Minimum score required to pass evaluation (default 65).
  - `scoring_weights`: Criteria and weights used by the LLM for scoring.
- **`llm`**:
  - Configures the AI provider, custom `base_url` (supporting local Ollama/vLLM endpoints), `model`, request delay, temperature (default 0.0), and timeout.
- **`telegram`**: Controls link previews and empty notifications.
- **`workers`**: Concurrency worker counts for fetching, evaluation, discovery, and pruning.

---

## 📝 Prompt Engineering Setup (`cv.md` & `preferences.md`)

`JobHunter` compiles a highly rigorous system prompt dynamically (`prompt.py`) combining your CV (`config/cv.md`) and preferences (`config/preferences.md`) with strict evaluation rules.

### Anti-Hallucination & Prompt Injection Guardrails

- **Untrusted Data Isolation**: Job postings are wrapped in explicit XML tags and treated strictly as data. The system prompt explicitly instructs the LLM never to follow instructions contained within job postings.
- **Strict Evidence Rule**: The LLM is prohibited from hallucinating skills, employers, numbers, or years of experience. A strength can _only_ be cited if the job posting explicitly requests it _and_ the CV explicitly demonstrates it.
- **Seniority & Gap Enforcement**: Minor seniority mismatches (1-2 years) are permissible if core skills match, but major gaps trigger hard failures or score penalties. Missing required skills _must_ be explicitly listed under gaps.
- **Structured JSON Output**: Enforces exact adherence to the `EvaluationResult` Pydantic model (reasoning, hard fails, strengths, gaps, score, score explanation, and one-sentence professional pitch).

---

## 🔌 Adding a Custom Source / Board

To extend `JobHunter` with a new Applicant Tracking System (ATS) or custom job board, follow this 4-step developer guide:

### Step 1: Create a New Adapter File

Create a new Python module in `src/jobhunter/sources/your_ats.py` inheriting from `BaseSource` (`sources/base.py`):

```python
import logging
import re

from jobhunter.core.http import fetch_url
from jobhunter.core.textutil import clean_html, parse_date
from jobhunter.models import Job
from jobhunter.sources.base import BaseSource

logger = logging.getLogger(__name__)


class Source(BaseSource):
  name = "your_ats"
  domains = ["yourats.com", "api.yourats.com"]
  url_patterns = [
    re.compile(r"yourats\.com/(?P<slug>[^/?#]+)"),
  ]
  is_aggregator = False
```

### Step 2: Implement Extraction Logic and Slug Validation

Implement the `fetch(self, slug: str = "", skip_parsing: bool = False, **kwargs)` method. When `skip_parsing` is `True`, make a lightweight test request or check to validate board existence (utilized by `discover` and `prune` tools via `validate_slug`):

```python
  def fetch(self, slug: str = "", skip_parsing: bool = False, **kwargs) -> list[Job]:
    """Fetches job listings from your custom ATS board API."""
    if not slug:
      raise ValueError(f"A company slug must be provided to fetch {self.name} jobs.")

    url = f"https://api.yourats.com/v1/boards/{slug}/jobs"
    data = fetch_url(url, expected_type=dict)

    if skip_parsing:
      return []

    jobs: list[Job] = []

    for item in data.get("jobs", []):
      job_id = str(item.get("id") or "")
      title = str(item.get("title") or "")
      job_url = str(item.get("url") or "")

      if not all([job_id, title, job_url]):
        continue

      jobs.append(
        Job(
          source=self.name,
          board=slug,
          company=slug.replace("-", " ").title(),
          job_id=job_id,
          title=title,
          url=job_url,
          location=str(item.get("location") or "Remote"),
          remote=True,
          posted=parse_date(item.get("created_at")),
          description=clean_html(item.get("description", "")),
        )
      )

    return jobs
```

### Step 3: Register the New Source

`src/jobhunter/sources/__init__.py` dynamically discovers all Python modules in the `sources/` directory. Because your module defines a `Source` class subclassing `BaseSource`, it is automatically imported and registered into the global `SOURCES` dictionary:

```python
# src/jobhunter/sources/__init__.py snippet:
for _, module_name, _ in pkgutil.iter_modules([current_dir]):
  if module_name == "base":
    continue
  module = importlib.import_module(f".{module_name}", package=__name__)
  if hasattr(module, "Source"):
    source_instance = module.Source()
    if getattr(source_instance, "enabled", True):
      SOURCES[source_instance.name] = source_instance
```

### Step 4: Configure Company Slugs in `config.json`

Add your new source name and company board slugs under the `companies` section in `config/config.json`:

```json
{
  "companies": {
    "greenhouse": ["stripe", "discord"],
    "lever": ["netflix"],
    "your_ats": ["acme-corp", "globex"]
  }
}
```
