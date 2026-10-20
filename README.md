# Job Hunter

Finds fresh **remote tech jobs**, lets an AI score each one against **your CV and preferences**, and sends the
good matches to your **Telegram**. It runs once a day on your computer or on GitHub Actions, and it needs no
third-party Python packages.

```
 job sites ──► fetch ──► filter ──► AI scoring ──► Telegram
 (many)        │         (your      (one request   (matches only,
               │          rules)     per job)       with a pitch line)
               └── remembers what it has already dealt with
```

- **Many sources:** Remotive, RemoteOK, Arbeitnow, plus the job boards of individual companies on Greenhouse, Lever,
  Ashby, Recruitee, Workable and Personio.
- **Your rules first:** cheap text filters (titles, skills, location, age) remove most jobs _before_ the AI sees any.
- **Honest scoring:** the AI must reject jobs that break your hard rules (wrong region, too senior, ...) and may only
  claim skills that are in your CV. The instructions it gets are built from your `config.json`
  (see `python -m jobhunter prompt`).
- **Never loses a job:** if a run crashes halfway, unfinished jobs are retried next time.
- **For any tech role:** presets for frontend, full-stack, backend, DevOps, data and mobile.

## Start here

```bash
git clone <this repo> job-hunter && cd job-hunter
python3 -m jobhunter init --preset fullstack --level junior   # creates config.json, cv.md, preferences.md, .env
# fill in cv.md, preferences.md and .env  (details: docs/GETTING_STARTED.md)
python3 -m jobhunter doctor                                   # checks your setup
python3 -m jobhunter run --dry-run                            # full test run: prints messages, sends nothing
python3 -m jobhunter run                                      # the real thing
```

**➡ The full step-by-step guide, with what you should see at each step, is [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md).**
It also covers getting the Telegram and AI keys, testing each stage on its own, scheduling it on GitHub Actions, and
troubleshooting.

## Commands

| Command                                      | What it does                                                                |
| -------------------------------------------- | --------------------------------------------------------------------------- |
| `init [--preset P] [--level L]`              | create your files from templates                                            |
| `doctor`                                     | check files and settings (offline)                                          |
| `prompt [--hide-cv]`                         | print the exact instructions the AI receives                                |
| `fetch [--ignore-seen] [--no-boards]`        | stage 1: get and filter jobs → `data/candidates.json`                       |
| `evaluate [--limit N] [--model M] [--out F]` | stage 2: AI scoring → `data/results.json`                                   |
| `send [--test] [--check] [--dry-run]`        | stage 3: Telegram, and remember finished jobs                               |
| `run [--dry-run]`                            | fetch + evaluate + send (what the daily schedule runs)                      |
| `discover`, `prune`                          | maintain your company lists (`discover` needs `python -m pip install ddgs`) |

## Project layout

```
jobhunter/                 the code (python -m jobhunter ...)
├── cli.py                 the commands
├── helpers/               shared building blocks: files, HTTP, text, config, the Job type
├── fetch/                 STAGE 1  sources/ (one file per job site), filters.py, stage.py
├── evaluate/              STAGE 2  prompt.py, llm.py, parsing.py, stage.py
├── send/                  STAGE 3  matches.py, telegram.py, stage.py
└── tools/                 init, doctor, prompt, discover, prune
tests/                     mirrors the code folders; no network needed
docs/                      GETTING_STARTED, CONFIG (every setting), ARCHITECTURE, CONTRIBUTING, MIGRATING
examples/                  config template, role presets, CV and preferences templates
.github/workflows/         the daily job and the test runner
```

Your own files are created in the project folder by `init` (`config.json`, `cv.md`, `preferences.md`, `.env`), and the tool
writes its working files to `data/`.

## Choosing the AI

In `config.json`, under `llm`:

| You want                                           | Settings                                                                                                                                                                          |
| -------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Gemini (default)                                   | `"provider": "openai"`, `"base_url": "https://generativelanguage.googleapis.com/v1beta/openai"`, `"model": "<a model from AI Studio>"`, `"request_delay": 5` for free-tier limits |
| OpenAI / OpenRouter / Groq / LM Studio / llama.cpp | `"provider": "openai"` with that service's `base_url` and `model`                                                                                                                 |
| Local Ollama                                       | `"provider": "ollama"`, `"base_url": "http://localhost:11434"`, `"model": "<a pulled model>"`                                                                                     |

Your CV and preferences are sent to the provider with every request. Leave your phone number, email and address
out of `cv.md`; scoring does not need them.

## Tuning

After a fetch, open `data/run_status.json`. Its `dropped` section counts how many jobs each filter removed. The rule
that drops the most is the one to loosen or tighten. Every setting and the order of the rules is in
**[docs/CONFIG.md](docs/CONFIG.md)**.

## Good to know

- **Be kind to the job sites.** Run it once a day. The aggregators ask API users to keep requests low.
- **Your CV stays out of git by default.** `.gitignore` hides `cv.md` and `preferences.md` so a public fork can't leak them.
  In a private repo, `git add -f cv.md preferences.md` commits them (see docs/GETTING_STARTED.md, step 7).
- **Only public feeds are used.** There is no LinkedIn or Indeed support: they have no public feeds and forbid scraping.
- **Coverage is uneven.** Aggregators and ATS boards favour tech companies; a given company may use none of them.
- **There is no "all companies" switch.** The company platforms only answer one company at a time. Run
  `python -m jobhunter discover --write` about weekly to grow your company list (`.github/workflows/discover.yml` automates it).
- **The score is a model's judgment**, guided by your weights. Treat it as a good first filter, not a verdict.

## Contributing

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md). Adding a new job site is one small file; [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
walks through it. Upgrading from the old script version? See [docs/MIGRATING.md](docs/MIGRATING.md).
