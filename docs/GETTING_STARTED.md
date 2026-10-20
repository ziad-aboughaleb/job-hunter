# Getting started

A complete walk-through, from nothing to a daily Telegram message. Every step says what you should see.
Budget about 15 minutes.

## 0. What you need

- **Python 3.8 or newer.** Check: `python3 --version`
- **Git** (to download the code), a **Telegram** account, and an **AI API key** (a free Gemini key from Google AI Studio works)
  or a local **Ollama** installation.
- No `pip install` is needed.

## 1. Get the code

```bash
git clone <this repo's URL> job-hunter
cd job-hunter
python3 -m unittest discover -s tests -t .      # optional sanity check: should end with "OK"
```

Run every command below from this folder (the one that holds `jobhunter/` and, soon, `config.json`).
On Windows use `python` instead of `python3`.

## 2. Create your files

```bash
python3 -m jobhunter init --preset fullstack --level junior
```

Pick the preset closest to the job you want and the level you are at (you can edit everything afterwards):

| `--preset`  | For                                                      |
| ----------- | -------------------------------------------------------- |
| `frontend`  | React / Vue / Angular, UI work                           |
| `fullstack` | JavaScript/TypeScript frontend + backend (MERN, Next.js) |
| `backend`   | APIs and services (Python, Node, Java, Go, ...)          |
| `devops`    | DevOps, SRE, platform, cloud                             |
| `data`      | data engineering, analytics, ML                          |
| `mobile`    | iOS, Android, React Native, Flutter                      |

| `--level` | Effect                                                                                |
| --------- | ------------------------------------------------------------------------------------- |
| `junior`  | also searches intern / trainee / graduate roles; drops senior, lead, staff, principal |
| `mid`     | drops senior-and-above and intern-level titles                                        |
| `senior`  | drops junior and intern-level titles                                                  |

You now have `config.json`, `cv.md`, `preferences.md` and `.env`, plus an empty `data/` folder.

## 3. Fill in the three personal files

**`cv.md`**: paste your CV as plain text. Include skills, years of experience, work history with the technologies used,
and projects. The AI may only claim skills that appear here. Leave out your phone, email and address (the text is sent
to the AI provider on every request).

**`preferences.md`**: replace every `<FILL IN>`. This file drives the AI's _hard gates_ (automatic rejections), so be
concrete. A filled-in example:

```markdown
## Seniority

- My years of professional experience: 1
- Levels I accept: junior, intern, trainee; postings asking for up to 2 years are fine
- Hard fail postings that require more than 4 years, or that are staff/principal level.

## Location and eligibility (HARD GATE)

- I can work from: Portugal
- Time zones I can overlap with: UTC-1 to UTC+3
- Hard fail if the posting restricts candidates to a country or region I am not in.
- Contractor / employer-of-record arrangements are OK: yes

## Work arrangement

- Fully remote only
```

**`.env`**: three values.

- `TELEGRAM_BOT_TOKEN`: in Telegram, message **@BotFather**, send `/newbot`, follow the prompts, copy the token.
- `TELEGRAM_CHAT_ID`: send your new bot any message, open `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser,
  and copy the number after `"chat":{"id":`. (Only a message _you_ sent to the bot makes it appear.)
- `LLM_API_KEY`: your AI key. For Gemini: Google AI Studio → "Get API key".

## 4. Adjust `config.json` (two minutes)

Open it and check these:

1. `profile.target_roles`: one phrase describing the roles you want. It is inserted into the AI's instructions
   ("The role is not mainly _this_"). The preset sets a sensible value.
2. `llm.model`: a model name your provider currently offers (names change; check the provider's list).
   Using Ollama instead? Set `"provider": "ollama"`, `"base_url": "http://localhost:11434"` and your model name.
3. `filters.location_exclude_terms` / `location_allow_terms`: places you cannot work from, e.g.
   `["united states", "usa", "us", "canada"]`, and words that rescue a listing, e.g. `["worldwide", "global", "emea"]`.
4. Optional: `companies`: company names to watch directly (see docs/CONFIG.md).

**Why there is no "fetch every company" switch.** Greenhouse, Lever, Ashby and the others only answer for one company
at a time; none of them publishes a list of all their companies. The aggregators in `boards` cover many companies without
a list, and for direct company boards the list has to be built. `python3 -m jobhunter discover --write` searches for company
names that match your `title_include` words and adds them to `config.json`. Running it about once a week is enough, and
`.github/workflows/discover.yml` does exactly that on a schedule (it also removes names that stopped existing).

## 5. Check the setup

```bash
python3 -m jobhunter doctor
```

Expected: every line starts with `ok`, ending with `All good.` Each `FIX` line tells you what is missing.

To see exactly what the AI will be told (rubric built from your config, then your CV and preferences):

```bash
python3 -m jobhunter prompt
```

## 6. Test each stage, one at a time

Do these in order. Each takes seconds to a few minutes.

**a) Telegram works**

```bash
python3 -m jobhunter send --test
```

A message "Telegram connection works" should arrive on your phone. If not: `HTTP 401` = wrong token;
`chat not found` = wrong chat id, or you never messaged the bot.

**b) Fetching works**

```bash
python3 -m jobhunter fetch
```

Prints something like `Sources: 2/2 reachable | jobs fetched: 1840`, then `Dropped: {...}` and
`Candidates written to data/candidates.json: 12`. Open `data/candidates.json` and check the jobs look relevant.
`data/run_status.json` shows how many jobs each filter removed: the biggest number is the filter to loosen or tighten
(rules and order: docs/CONFIG.md).

- Zero candidates? Loosen a filter (`min_stack_hits`, `max_age_days`, `title_exclude`).
- Hundreds of irrelevant ones? Tighten `title_include` / `stack_keywords`.

**c) The AI scoring works** (try only 3 jobs first)

```bash
python3 -m jobhunter evaluate --limit 3
```

One line per job: `[1/3] J1 'Frontend Developer' -> score 82 (2s)` or `-> hard_fail: <reason>`.
Errors are explained in plain words: `authentication failed` (check `LLM_API_KEY`), `model or endpoint not found`
(fix `llm.model`), `cv.md is empty or still the placeholder`.
Hard fails for reasons you disagree with mean `preferences.md` needs to be clearer.

**d) The messages look right** (prints them, sends nothing, saves nothing)

```bash
python3 -m jobhunter send --dry-run
```

**e) The whole pipeline, still harmless**

```bash
python3 -m jobhunter run --dry-run
```

**f) The real thing**

```bash
python3 -m jobhunter run
```

Matching jobs arrive on Telegram, followed by a short summary. Run it a second time: it should report that there are no
new jobs, because finished jobs are remembered in `data/seen.json`.

> **Changed your mind about preferences after a real run?** Finished jobs are not looked at again. To re-evaluate them,
> run `python3 -m jobhunter fetch --ignore-seen` (or delete `data/seen.json`).

## 7. Run it every day

**GitHub Actions** (free, nothing to keep running):

1. Make a **private** copy of the repo (use "Use this template"/fork, then set it private), or keep it public and use
   the `CV_MD` / `PREFERENCES_MD` secrets below so no personal text is committed.
2. Repo → Settings → Secrets and variables → Actions → **New repository secret** for each of:
   `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `LLM_API_KEY`.
   Optional: `CV_MD` (the contents of `cv.md`), `PREFERENCES_MD`, `CONFIG_JSON` (the contents of `config.json`).
   If you don't use these three secrets, commit the files instead, **in a private repo only**:
   `git add -f cv.md preferences.md config.json && git commit -m "Add my files" && git push`.
   (`-f` adds files that `.gitignore` hides, so you never edit `.gitignore`, and later updates from the public repo don't
   conflict. Once added, changes to those files are tracked normally.)
   `.gitignore` hides `cv.md` and `preferences.md` on purpose: GitHub's Fork button always makes a _public_ copy, so an
   ignored CV can't be pushed to a public fork by accident.
3. Edit the cron line in `.github/workflows/job-hunter.yml`. GitHub cron is **UTC**.
4. Actions tab → **job-hunter** → **Run workflow**, tick **Dry run**, run it, and read each step's log.
5. Run it again without Dry run. A commit "chore: update seen jobs" appears as a commit on your `main` branch: that
   is the memory between runs. If that step fails with a permissions error:
   Settings → Actions → General → Workflow permissions → **Read and write permissions**.
6. Optional extra runs: the workflow has two commented-out cron lines that poll only your listed companies
   (`--no-boards`), so you catch new company postings faster without hitting the aggregators more than once a day.

**Your own computer** (`crontab -e`):

```
0 8 * * *  cd /path/to/job-hunter && python3 -m jobhunter run >> data/run.log 2>&1
```

The computer must be on, and Ollama (if you use it) running, at that time.

## 8. Running the automated tests

These check the _code_, not your setup. They never use the network or your keys.

```bash
python3 -m unittest discover -s tests -t .                 # everything: ends with "OK"
python3 -m unittest discover -s tests/fetch -t .           # one area (helpers, fetch, evaluate, send, tools)
python3 -m unittest tests.fetch.test_filters -v            # one file, with every test name
```

Run them after any change to the code. `tests/test_pipeline.py` runs fetch → evaluate → send end to end with the
network faked. The test folders mirror the code folders, so `jobhunter/fetch/filters.py` is tested in
`tests/fetch/test_filters.py`.

## Troubleshooting

| Symptom                                      | Fix                                                                                                        |
| -------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `doctor` says `FIX`                          | Do what that line says; run `doctor` again                                                                 |
| `WARNING (config.json): unknown setting ...` | A setting name is misspelled; it is being ignored                                                          |
| `board not found (404)` for a company        | Wrong or outdated company name. `python3 -m jobhunter prune` removes them                                  |
| `Every source failed`                        | No internet, or a typo in `config.json`                                                                    |
| `authentication failed`                      | Wrong API key, or the variable named in `llm.api_key_env` is not set                                       |
| `model or endpoint not found`                | `llm.model` or `llm.base_url` is wrong; the provider may have retired the model                            |
| `invalid model output twice`                 | Raise `llm.max_output_tokens`, or set `"json_mode": "object"`, or try another model                        |
| Rate-limit errors from the AI                | Raise `llm.request_delay` (free tiers often need 5)                                                        |
| Nothing arrives on Telegram                  | `send --test`; check token/chat id; make sure you messaged the bot first                                   |
| Same jobs sent again                         | `data/seen.json` is not being saved (a read-only folder, or on GitHub Actions the commit step failed)      |
| Too few matches                              | Read `data/run_status.json` `dropped` counts, then loosen filters; check `preferences.md` isn't too strict |
