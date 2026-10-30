# JobHunter 🎯

> **AI-Powered, Highly Concurrent, Zero-Database Automated Job Hunting Pipeline**

`JobHunter` is a robust, production-grade Python CLI application designed to fully automate the job search and filtering lifecycle. It continuously scrapes Applicant Tracking Systems (ATS) and job boards, filters opportunities against precise regex and keyword criteria, evaluates candidate-job fit using Large Language Models (LLMs) with strict JSON schemas, and dispatches rich real-time alerts directly to Telegram.

---

## 🚀 Key Features

- **High Concurrency & Rate Limiting**: Powered by `concurrent.futures` with dynamic worker bounds, exponential backoff retries on transient network errors, and intelligent request pacing.
- **ATS WAF & API Bypass**: Bypasses heavy frontend anti-bot walls by querying official public underlying JSON/XML board APIs directly (Greenhouse, Lever, Personio, Workable, Recruitee, Ashby, plus aggregators like Remotive, RemoteOK, and Arbeitnow).
- **Multi-Stage Filtering**: Filters jobs through regex word-boundary matching for titles, excluded companies, location rules, remote requirements, posting age, and minimum tech stack keyword hits (`stack_hits`).
- **AI-Driven Evaluation**: Evaluates shortlisted candidates against your exact CV (`config/cv.md`) and preferences (`config/preferences.md`) using OpenAI-compatible LLMs, enforcing hard gates, scoring rubrics, and anti-hallucination guardrails.
- **Telegram Rich Alerts**: Dispatches beautifully formatted HTML notifications featuring VIP priority badges, score color-coding, AI reasoning, score breakdowns, professional pitches, and direct links.
- **Autonomous Maintenance Tools**: Includes built-in CLI commands to automatically discover new company career boards via DuckDuckGo and prune dead or broken board URLs.
- **Zero-Database State Management**: Uses atomic file writes with file locking (`filelock`) and a rolling 90-day retention cache (`seen.json`) to prevent duplicate processing without requiring an external database.

---

## 🛠️ Quickstart Guide

### Prerequisites

- **Python >= 3.14**
- **uv** (recommended Python package and project manager)

### 1. Clone & Install

```bash
git clone https://github.com/ziad-aboughaleb/job-hunter-v2.git
cd job-hunter-v2
uv sync
```

### 2. Configure Environment Variables

Copy the example environment file and add your API keys:

```bash
cp .env.example .env
```

Edit `.env`:

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_telegram_chat_id_here
LLM_API_KEY=your_openai_or_compatible_api_key_here
```

### 3. Set Up Configuration & Profile

Create or copy configuration files in the `config/` directory (examples are provided in `examples/`):

```bash
cp examples/config.example.json config/config.json
cp examples/preferences.example.md config/preferences.md
# Create your cv.md in config/
cp examples/cv.example.json config/cv.md # (rename or write as Markdown)
```

> **💡 Note on Environment Fallbacks & GitHub Actions:**
> `JobHunter` automatically falls back to environment variables (`CONFIG_JSON`, `CV`, `PREFERENCES`) if physical configuration files do not exist on disk. This allows deploying via GitHub Actions on public repositories using GitHub Secrets instead of committing sensitive files.

### 4. Run the Pipeline

Execute the full pipeline (Fetch -> Evaluate -> Send):

```bash
uv run jobhunter run
```

---

## 🔄 The 5-Stage Pipeline

```
[Discover / Configure] ──> [Fetch & Filter] ──> [AI Evaluate] ──> [Send to Telegram] ──> [State Purge & Seen Sync]
```

1. **Discover / Configure**: Resolve targets from `config.json` or discover new company boards using `jobhunter discover`.
2. **Fetch**: Scrape raw job postings concurrently across configured ATS boards and aggregators.
3. **Filter & Prune**: Discard duplicates, previously seen jobs, and postings failing title, location, age, or stack keyword criteria. Rank candidates by VIP priority and stack keyword hits.
4. **Evaluate**: Submit shortlisted candidates to the LLM. Enforce hard gates and score against your CV and preferences.
5. **Send & Purge**: Dispatch passing job alerts to Telegram. Log processed jobs to `seen.json` with a 90-day retention window and purge completed items from active state files.

---

## 📖 Documentation Deep Dives

For comprehensive technical documentation, consult the `docs/` folder:

- **[Architecture Guide](docs/architecture.md)**: Detailed breakdown of the decoupled pipeline modules, concurrency model, and zero-database state lifecycle.
- **[Configuration & Settings](docs/configuration.md)**: Comprehensive guide to `config.json`, Pydantic settings, environment variables, and prompt engineering setup (`cv.md` / `preferences.md`).

---

## 💻 CLI Commands Reference

| Command              | Description                                           | Key Options                                                                     |
| :------------------- | :---------------------------------------------------- | :------------------------------------------------------------------------------ |
| `jobhunter run`      | Runs the full pipeline (fetch -> evaluate -> send)    | `-s, --source`, `--no-aggregators`, `--ignore-seen`, `-l, --limit`, `--dry-run` |
| `jobhunter fetch`    | Scrapes and filters jobs from configured boards       | `-s, --source`, `--no-aggregators`, `--ignore-seen`, `-l, --limit`              |
| `jobhunter evaluate` | Scores and evaluates pending candidates using AI      | `-j, --job <UID>`                                                               |
| `jobhunter send`     | Dispatches passing job evaluations to Telegram        | `--dry-run`                                                                     |
| `jobhunter discover` | Discovers new company ATS slugs via DuckDuckGo        | `-w, --write`, `-s, --source`, `-t, --titles`                                   |
| `jobhunter prune`    | Validates and prunes broken company slugs from config | `-w, --write`, `-s, --source`                                                   |
| `jobhunter prompt`   | Prints the compiled AI evaluation system prompt       | None                                                                            |
