# config.json reference

Every setting has a default, so `config.json` only needs the settings you change. Names that start with `_`
(like `"_help"`) are notes and are ignored. Misspelled settings are reported as warnings when any command starts.

## How a job travels (and where each setting acts)

```
fetch (filters + limits + boards/companies) ──► candidates ──► evaluate (llm + profile + scoring) ──► send (score_threshold + telegram)
```

## `profile`

| Key            | Default      | Meaning                                                                                                                                                                 |
| -------------- | ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `target_roles` | generic text | Describes the roles you want. It is inserted into the AI's _role_ hard gate: "The role is not mainly `<target_roles>`." Be specific: `"backend engineering in Python"`. |

## `boards`: aggregator sites

`true`/`false`, or an object with options (`{"enabled": true, "category": "devops"}`).

| Board       | Options                                                                          | Notes                         |
| ----------- | -------------------------------------------------------------------------------- | ----------------------------- |
| `remotive`  | `category` (default `software-dev`; others e.g. `devops`, `data`), `limit` (300) | one request per run           |
| `remoteok`  | none                                                                             |                               |
| `arbeitnow` | `pages` (2)                                                                      | mostly Europe; off by default |

## `companies`: specific companies to watch (optional)

There is no public list of all companies on these platforms, so there is no "all companies" setting. Grow this list with
`python -m jobhunter discover --write` (about weekly is enough; `.github/workflows/discover.yml` automates it).

Lists of company names as they appear in the company's job-board URL.

| Key                 | URL pattern                                       |
| ------------------- | ------------------------------------------------- |
| `greenhouse`        | `job-boards.greenhouse.io/<name>`                 |
| `lever`, `lever_eu` | `jobs.lever.co/<name>`, `jobs.eu.lever.co/<name>` |
| `ashby`             | `jobs.ashbyhq.com/<name>`                         |
| `recruitee`         | `<name>.recruitee.com`                            |
| `workable`          | `apply.workable.com/<name>`                       |
| `personio`          | `<name>.jobs.personio.de` or `.com`               |

A name that does not exist is reported as "board not found"; `python -m jobhunter prune` removes those.
Duplicates that differ only by case are ignored.

## `filters`: what reaches the AI

Rules run **in this order**; the first one that rejects a job wins. `data/run_status.json` → `dropped` counts rejections per reason.

| #   | Reason in `dropped` | Setting                                          | How it matches                                                                                                                              |
| --- | ------------------- | ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `company_excluded`  | `company_exclude`                                | company name contains the text, ignoring case and punctuation (`"meta"` also matches "Metabase")                                            |
| 2   | `title_no_match`    | `title_include`                                  | the title must contain at least one of these (plain text, so `"react"` matches "ReactJS")                                                   |
| 3   | `title_excluded`    | `title_exclude`                                  | **whole words**: `"java"` does not match "JavaScript"; `"sr."`, `".net"`, `"c++"` work                                                      |
| 4   | `not_remote`        | `require_remote`                                 | the site flags it remote, or the location/title says "remote" (or the description does, if there is no location)                            |
| 5   | `location_excluded` | `location_exclude_terms`, `location_allow_terms` | whole words in the **location field only**. An allow term rescues a job that also has an exclude term (`"Remote - US or Worldwide"` passes) |
| 6   | `location_missing`  | `location_require_terms`                         | if the list is not empty, the location must contain one of the terms. Example for local jobs: `require_remote: false`, `["berlin"]`         |
| 7   | `too_old`           | `max_age_days`                                   | postings with no date are kept                                                                                                              |
| 8   | `stack_mismatch`    | `stack_keywords`, `min_stack_hits`               | whole words in title + description; a job needs `min_stack_hits` _different_ keywords                                                       |

`company_priority` (not a rejection rule): jobs from these companies skip rule 8 and are never cut by
`max_candidates_per_run`; they also get a ⭐ in Telegram. All other rules still apply to them.

Notes

- Rules only see the posting's metadata and text. A restriction that appears only in the description ("US residents
  only") passes the location rule and is caught later by the AI's hard gates, using your `preferences.md`.
- Term lists are case-insensitive.

## `limits`

| Key                      | Default | Meaning                                                                   |
| ------------------------ | ------- | ------------------------------------------------------------------------- |
| `max_candidates_per_run` | 30      | most jobs sent to the AI per run (extra ones return next run, best first) |
| `description_max_chars`  | 7000    | longest description kept per job                                          |
| `max_messages`           | 15      | most Telegram job cards per run (extra matches are sent next run)         |
| `seen_retention_days`    | 90      | how long finished jobs are remembered                                     |
| `fetch_workers`          | 8       | sources fetched in parallel                                               |

## Scoring

| Key               | Default                | Meaning                                                                                                                        |
| ----------------- | ---------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `score_threshold` | 75                     | score needed for a Telegram message. The AI's instructions use the same number, so changing it is safe                         |
| `scoring_weights` | 4 factors, 40/20/20/20 | list of `{"name", "weight", "what"}`. Rewrite them for your field (weights should add up to 100). `doctor` warns if they don't |

## `llm`

| Key                   | Default                  | Meaning                                                                                                                     |
| --------------------- | ------------------------ | --------------------------------------------------------------------------------------------------------------------------- |
| `provider`            | `openai`                 | `openai` = any OpenAI-compatible API; `ollama` = local server                                                               |
| `base_url`            | Gemini's OpenAI endpoint | the API address (for Ollama: `http://localhost:11434`)                                                                      |
| `model`               | `gemini-3.5-flash-lite`  | model name. Names change over time: check your provider's list                                                              |
| `api_key_env`         | `LLM_API_KEY`            | name of the environment variable that holds the key (put it in `.env`)                                                      |
| `temperature`         | 0                        | keep at 0 for repeatable scoring                                                                                            |
| `timeout`             | 600                      | seconds to wait for one answer                                                                                              |
| `num_ctx`             | 32768                    | context size; also used to size the job text. For small local models use 8192                                               |
| `max_output_tokens`   | 2500                     | answer length limit. Thinking models need room; the tool doubles it automatically if an answer is cut off                   |
| `json_mode`           | `schema`                 | `schema` (strict) or `object` (plain JSON mode). The tool falls back to `object` by itself if the provider rejects `schema` |
| `request_delay`       | 0                        | seconds between jobs. Free tiers usually need about 5                                                                       |
| `extra_body`          | `{}`                     | extra fields merged into every request, e.g. `{"reasoning_effort": "low"}`                                                  |
| `think`, `keep_alive` | `false`, `30m`           | Ollama only                                                                                                                 |

## `telegram`

| Key               | Default | Meaning                                                                  |
| ----------------- | ------- | ------------------------------------------------------------------------ |
| `link_preview`    | `false` | show link previews in messages                                           |
| `notify_on_empty` | `true`  | send a short "nothing found today" message (also makes failures visible) |

## Environment variables (`.env`)

`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and the variable named in `llm.api_key_env`. Real environment variables
(for example CI secrets) win over `.env`, unless they are empty.

## What shapes the AI's rubric

The instructions the AI receives are **built from your config every run**. Run `python -m jobhunter prompt` to see them.

| Part of the instructions                                                                   | Comes from                                                                         |
| ------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------- |
| "The role is not mainly ..." hard gate                                                     | `profile.target_roles`                                                             |
| The weighted scoring factors (names, weights, what each means)                             | `scoring_weights`                                                                  |
| "Most postings should score below N", the score bands, and "leave the pitch empty below N" | `score_threshold`                                                                  |
| Location, work-arrangement, seniority and dealbreaker hard gates                           | the **text of `preferences.md`** (the gates say "per the candidate's preferences") |
| The candidate's skills and experience                                                      | the **text of `cv.md`**                                                            |
| The description text per job (how much of it)                                              | `limits.description_max_chars`, `llm.num_ctx`                                      |

What is **not** dynamic: the persona ("strict recruiter"), the security paragraph, the wording of the generic hard gates,
the evidence rules, and the answer format are fixed in `jobhunter/evaluate/prompt.py`. The `filters` section
never reaches the AI at all: filters run before it, and a job they remove is never scored. For example, your
`location_exclude_terms` shape which jobs arrive, while the AI's location judgment comes from `preferences.md`.
