# Architecture

This page explains how the code fits together, so you can read it, change it, or extend it.

## The big picture

The tool has **three stages**. They never call each other: each reads files written by the one before and writes its
own. That keeps every stage small, testable on its own, and safe to re-run.

```
                 config.json                    cv.md + preferences.md          .env
                     │                                  │                         │
  ┌──────────┐  data/candidates.json  ┌───────────┐  data/results.json  ┌───────────┴─┐
  │  fetch   │ ─────────────────────► │ evaluate  │ ───────────────────►│    send     │──► Telegram
  └──────────┘  data/run_status.json  └───────────┘                     └──────┬──────┘
   sources + filters                    one AI request per job                  │
                                                                        data/seen.json (what is finished)
```

`python -m jobhunter run` just runs the three stages in order (and always runs `send`, so a failure still produces an alert).

## Folder layout

Each pipeline stage is one folder with a `stage.py` that holds its entry point, `run()`. Start reading there.

```
jobhunter/
├── cli.py              the commands; each calls one run() function
├── helpers/            shared building blocks (no job-hunting rules in here)
│   ├── paths.py        where files live (project folder, data/)
│   ├── store.py        reading/writing JSON files atomically; seen.json helpers
│   ├── http.py         GET/POST with retries on top of urllib; separates "unreachable" from "server said no"
│   ├── textutil.py     HTML to text, date parsing, whole-word matching
│   ├── config.py       defaults, loading config.json, typo/mistake warnings, .env
│   └── models.py       the Job dataclass every source produces
├── fetch/              STAGE 1
│   ├── sources/        one module per website + the registry in __init__.py
│   ├── filters.py      JobFilter: the rules that run before the AI
│   └── stage.py        fetch every source, filter, rank, write candidates.json
├── evaluate/           STAGE 2
│   ├── prompt.py       the rubric (built from config.json + CV + preferences), the answer schema
│   ├── llm.py          LLMClient: one request to Ollama or an OpenAI-compatible API, with fallbacks
│   ├── parsing.py      repair and validate the model's reply
│   └── stage.py        the loop: one independent request per job
├── send/               STAGE 3
│   ├── matches.py      validate results.json, pick matches, decide what is "seen"
│   ├── telegram.py     format (with escaping) and send
│   └── stage.py        send the cards and a summary, update seen.json
└── tools/              init_project.py, doctor.py, show_prompt.py, discover.py, prune.py
```

`tests/` mirrors this layout: `jobhunter/fetch/filters.py` is tested in `tests/fetch/test_filters.py`.

## Where to start reading

1. `helpers/models.py`: the `Job` object everything revolves around (30 lines).
2. `fetch/sources/greenhouse.py`: a typical source: fetch JSON, return `Job` objects.
3. `fetch/filters.py`: the rules, one small method each, with a table of reasons at the top.
4. `fetch/stage.py`: stage 1, top to bottom.
5. `evaluate/prompt.py` → `llm.py` → `parsing.py` → `stage.py`: stage 2.
6. `send/matches.py`, especially the rule about what counts as "seen", then `send/stage.py`.
7. `cli.py`: how the commands map onto the stages.

## Files the tool writes (`data/`)

| File              | Written by | Contents                                                                                                                 |
| ----------------- | ---------- | ------------------------------------------------------------------------------------------------------------------------ |
| `candidates.json` | fetch      | list of `{ref, uid, company, title, url, location, posted, priority, stack_hits, description}`. `ref` is `J1`, `J2`, ... |
| `run_status.json` | fetch      | counts, `dropped` per filter reason, source errors                                                                       |
| `results.json`    | evaluate   | list of `{ref, score, hard_fail, strengths, gaps, pitch}`; one entry per evaluated job                                   |
| `seen.json`       | send       | `{uid: date}` for jobs that are finished                                                                                 |

`fetch` deletes `candidates.json`, `results.json` and `run_status.json` when it starts, so a failed run can never be
mistaken for a fresh one.

## Design decisions (and why)

- **Files between stages.** Easy to inspect while debugging, trivial to re-run one stage, and no shared state in memory.
- **Code does the exact work, the AI does judgment.** Fetching, filtering, formatting, escaping and state are plain code.
  The model only scores and explains. A job can never reach Telegram unless it passed the code's own validation.
- **One independent AI request per job.** Context never accumulates, a failure affects one job, and no agent
  framework or tool-calling is needed. The CV is part of every request, which servers like Ollama cache.
- **Answer format is enforced and then re-checked.** A JSON schema is requested, and the reply is validated anyway
  (`evaluate/parsing.py: normalize`): fences are stripped, a missing score is an error (never a silent 0), wrong types are repaired.
  One corrective retry tells the model what was wrong.
- **"Seen" means finished** (`send/matches.py: record_seen`). Evaluated non-matches and delivered matches are marked; everything
  else (not evaluated, failed to send, held back by the cap) is retried next run. A crash never loses a job.
- **Whole-word matching** for exclusion and location terms (`helpers/textutil.py: term_in`). Substring matching made "java" drop
  JavaScript jobs and "usa" match "Lusaka". Inclusion uses plain substrings on purpose (recall over precision), because
  the stack rule filters the noise afterwards.
- **Standard library only.** Nothing to install, nothing to break. (`ddgs` is optional and only for `discover`.)

## Extending

### Add a job site

1. Create `jobhunter/fetch/sources/mysite.py`:

```python
"""MySite: https://api.mysite.example/jobs/<company>"""
from typing import List, Optional

from jobhunter.helpers import http
from jobhunter.helpers.models import Job
from jobhunter.helpers.textutil import clean_html, parse_date, pretty_company


def fetch(slug: str) -> Optional[List[Job]]:
    data = http.get_json(f"https://api.mysite.example/jobs/{slug}")
    if data is None:                       # 404: no such company
        return None
    return [
        Job(source="mysite", board=slug, company=pretty_company(slug),
            job_id=str(item["id"]), title=item["title"], url=item["url"],
            location=item.get("location", ""), remote=True if item.get("remote") else None,
            posted=parse_date(item.get("posted_at")), description=clean_html(item.get("body")))
        for item in data["jobs"]
    ]
```

2. Register it in `jobhunter/fetch/sources/__init__.py`: add `"mysite": mysite.fetch` to `COMPANY_SOURCES`
   (or to `BOARD_SOURCES` for an aggregator whose `fetch(options)` takes the config options and returns jobs).
3. Add a test in `tests/fetch/test_sources.py` with a small copy of the real response (see the existing ones).
4. Mention it in `docs/CONFIG.md`.

Rules of thumb: return `None` only for "no such board"; let real failures raise (the caller reports them and moves
on); set `remote=True` only if the site says so; strip HTML with `clean_html`.

### Add a filter rule

Add a method to `JobFilter` (in `fetch/filters.py`) that returns a reason string or `None`, add it to the tuple in `reject_reason()` at the
right position, document it in the table at the top of `filters.py` and in `docs/CONFIG.md`, and add default values
in `config.py` (`DEFAULTS["filters"]`). Test it in `tests/fetch/test_filters.py`.

### Support another AI API

If it speaks the OpenAI chat format, no code is needed: set `llm.base_url` and `llm.model`. For a different protocol,
add a method to `LLMClient` in `evaluate/llm.py` (see `_openai` and `_ollama`), dispatch to it in `complete()`, and allow the new name in
`config.validate()` and `LLMClient.__init__`. Raise `LLMFatal` for problems that affect every job (bad key) and
`TruncatedOutput` when the answer is cut off.

### Send somewhere other than Telegram

`send/telegram.py` has two functions: `format_card(job, result)` and `send_message(...)`. Write a module with the same two
functions for your service (remember to escape anything that comes from a posting) and call it from `send/stage.py`.

### Change what the AI is told

Everything is in `evaluate/prompt.py`; `python -m jobhunter prompt` prints the result. `config.json` already controls the target roles, the weights and the
threshold; edit `hard_gates()` or the template for anything beyond that.

## Testing

`python -m unittest discover -s tests -t .` runs the whole suite in well under a second. **No test uses the network**: tests
replace `jobhunter.http.get_text` / `post_json` (and `telegram.send_message`) with fakes. `tests/support.py` gives
each test an empty project folder. `tests/test_pipeline.py` runs fetch → evaluate → send end to end.
