# Architecture & Pipeline Deep Dive

`JobHunter` is engineered as a decoupled, highly concurrent, zero-database Python pipeline. This document provides a deep architectural breakdown of its modules, state management lifecycle, and concurrency model.

---

## 🏗️ Core Module Architecture

The application logic is organized into clean, single-responsibility modules located in `src/jobhunter/`:

```
src/jobhunter/
├── main.py             # Typer CLI entrypoint and command router
├── models.py           # Pydantic data models (Job, Candidate, EvaluationResult, EvaluatedCandidate)
├── core/
│   ├── settings.py     # Pydantic Settings & configuration loading
│   ├── paths.py        # Atomic file I/O, path resolution, and file locking
│   ├── http.py         # Robust HTTP client with retries and exponential backoff
│   ├── filters.py      # Regex word-boundary filters and scoring utilities
│   ├── textutil.py     # HTML cleaning and date parsing utilities
│   └── logger.py       # Rich console and logging configuration
├── pipeline/
│   ├── fetch.py        # Stage 1-3: Scraping, filtering, deduplication, and scoring
│   ├── evaluate.py     # Stage 4: AI evaluation via OpenAI/LLM API
│   └── send.py         # Stage 5: Telegram dispatch and state lifecycle management
└── tools/
    ├── discover.py     # DuckDuckGo-powered company ATS board discovery
    ├── prune.py        # Automated dead board validation and pruning
    └── prompt.py       # Compiled system prompt inspection tool
```

### 1. Fetch & Filter Pipeline (`fetch.py`)

- **Task Generation**: Iterates through registered sources (`SOURCES`), matching non-aggregator sources with company slugs defined in `config.json` (e.g., `companies.greenhouse = ["stripe"]`). Aggregators (Remotive, RemoteOK, Arbeitnow) operate without slugs.
- **Concurrent Scraping**: Dispatches fetch tasks across a `ThreadPoolExecutor` bounded by `settings.workers.fetch_workers`.
- **Filtering & Deduplication**: Passes raw `Job` instances through `passes_all_filters()` (checking title include/exclude, company exclusions, location rules, remote requirements, posting age, and minimum stack hits). Removes cross-source duplicates and jobs already recorded in `seen.json`.
- **Prioritization & Capping**: Ranks passing jobs by VIP priority status (`company_priority`) and stack keyword hits (`stack_hits`). Enforces `max_candidates_per_run` and atomically writes the resulting candidates to `data/candidates.json`.

### 2. AI Evaluation Pipeline (`evaluate.py`)

- **Task Loading**: Reads `data/candidates.json` and `data/evaluated.json`, isolating candidates that have not yet been evaluated.
- **Structured LLM Calls**: Submits each candidate along with the compiled system prompt (containing the candidate CV, preferences, hard gates, and scoring rubric) to the OpenAI-compatible LLM client. Enforces `response_format={"type": "json_object"}`.
- **Validation**: Parses and validates the LLM response against the `EvaluationResult` Pydantic model.
- **Persistence**: Sorts evaluated candidates by match score descending and atomically persists them to `data/evaluated.json`.

### 3. Telegram Dispatch & State Management (`send.py`)

- **Dispatch**: Loads evaluated candidates from `evaluated.json` where `evaluation.hard_fail` is `False`. Formats rich HTML messages (including priority badges, score emojis, reasoning, score explanation, pitch, and job URL) and sends them to Telegram via `httpx` with 1-second request pacing.
- **State Lifecycle & Pruning**: Upon successful processing:
  1. Records all evaluated job UIDs into `data/seen.json` mapped to their current Unix timestamp (`int(time.time())`).
  2. Executes a **90-day retention prune** on `seen.json`, discarding any entry older than `settings.limits.seen_retention_days * 86400` seconds to prevent file bloat.
  3. Purges processed UIDs from `data/candidates.json`.
  4. Cleans up `evaluated.json` (preserving any items that failed delivery).

### 4. Discovery Tool (`discover.py`)

- Queries DuckDuckGo (`site:{domain} "{title}"`) for active company career boards across supported ATS providers (Greenhouse, Lever, Ashby, Personio, Workable, Recruitee).
- Extracts company slugs using regular expression patterns.
- Concurrently validates discovered slugs against ATS APIs. If run with `--write`, automatically merges valid new slugs into `config/config.json`. Includes a circuit breaker triggering after 3 consecutive search errors.

### 5. Pruning Tool (`prune.py`)

- Reads configured company slugs from `config/config.json`.
- Concurrently validates each slug against ATS APIs. Treats 404 and 410 HTTP status codes as definitive dead links (`SlugStatus.INVALID`).
- If run with `--write`, removes broken slugs from `config/config.json`.

### 6. Source Adapters (`sources/`)

- **Lightweight API-First Design**: `JobHunter` entirely avoids heavy, resource-intensive headless browsers (such as Selenium or Playwright) by querying public, lightweight JSON and XML ATS APIs directly. This ensures lightning-fast execution, minimal memory footprint, and high concurrency.
- **Aggregators vs. ATS Board Scrapers**:
  - **Aggregators** (`remotive.py`, `remoteok.py`, `arbeitnow.py`): Pull global remote job feeds without requiring company slugs (`is_aggregator = True`).
  - **ATS Board Scrapers** (`greenhouse.py`, `lever.py`, `ashby.py`, `personio.py`, `workable.py`, `recruitee.py`): Fetch job openings specifically via company board slugs (e.g., Greenhouse API endpoint `https://boards-api.greenhouse.io/v1/boards/{slug}/jobs`).
- **Slug Validation & Lifecycle (`validate_slug`)**: Both the `discover` and `prune` tools inherit from `BaseSource` and utilize the `validate_slug(slug)` method. By executing lightweight test queries or checking HTTP status codes (where 404 and 410 represent definitive dead links), `validate_slug` returns a `SlugStatus` enum (`VALID`, `INVALID`, or `UNKNOWN`) to ensure all tracked boards remain active.

---

## 🔄 State Management Lifecycle

`JobHunter` maintains state entirely in flat JSON files within the `data/` directory, protected against race conditions and concurrent execution anomalies:

```
[candidates.json] ──(Evaluated)──> [evaluated.json] ──(Sent & Synced)──> [seen.json (90-day retention)]
```

- **`data/candidates.json`**: Active pool of filtered, un-evaluated candidates waiting for AI scoring.
- **data/evaluated.json**: Storage for candidates that have undergone AI evaluation.
- **data/seen.json**: Persistent dictionary mapping job unique identifiers (`uid`) to their discovery/processing timestamp (`{uid: timestamp}`). Prevents re-scraping or re-evaluating the same job across runs, bounded by a 90-day rolling window.
- **Concurrency & Atomic Safety (`paths.py`)**: All write operations utilize `filelock.FileLock` (using lockfiles stored in `.locks/`) combined with atomic replacement (`tempfile.mkstemp` + `os.replace` + `os.fsync`/`fdatasync`), ensuring zero file corruption even under high concurrency or abrupt termination.

---

## ⚡ Concurrency & Rate-Limiting Model

`JobHunter` leverages Python's `concurrent.futures.ThreadPoolExecutor` for maximum concurrency while respecting API rate limits:

- **Configurable Worker Bounds**: Each pipeline stage reads worker allocations from `settings.workers`, strictly clamped between 1 and 20 threads (discovery clamped to 10):
  - `fetch_workers` (default: 8)
  - `evaluation_workers` (default: 1)
  - `discovery_workers` (default: 8)
  - `pruning_workers` (default: 8)
- **Exponential Backoff**: HTTP requests (`http.py`) automatically retry transient errors (HTTP 408 Request Timeout, 429 Too Many Requests, and 5xx Server Errors) with exponential backoff (`backoff * (2 ** attempt)`).
- **Request Pacing**:
  - LLM requests include an optional configurable delay (`settings.llm.request_delay`, default 5s).
  - Telegram dispatches include a fixed 1-second delay (`time.sleep(1)`) to comply with Telegram Bot API rate limits (1 message/second per chat).
