# Migrating from the script version (v2)

The v2 layout was a handful of scripts (`fetch_jobs.py`, `evaluate_jobs.py`, `send_telegram.py`, ...). v3 is a package, grouped into folders per stage,
with the same behaviour, a clearer structure, tests, and more settings. **Your `config.json` keeps working.**

| v2                                                           | v3                                                               |
| ------------------------------------------------------------ | ---------------------------------------------------------------- |
| `python3 fetch_jobs.py [--ignore-seen] [--no-boards]`        | `python -m jobhunter fetch [--ignore-seen] [--no-boards]`        |
| `python3 evaluate_jobs.py [--model M] [--out F] [--limit N]` | `python -m jobhunter evaluate [--model M] [--out F] [--limit N]` |
| `python3 send_telegram.py [--test] [--check] [--dry-run]`    | `python -m jobhunter send [--test] [--check] [--dry-run]`        |
| `run_pipeline.sh`                                            | `python -m jobhunter run [--dry-run]`                            |
| `python3 discover_companies.py`                              | `python -m jobhunter discover`                                   |
| `python3 prune_companies.py`                                 | `python -m jobhunter prune`                                      |
| (none)                                                       | `python -m jobhunter init`, `doctor` and `prompt`                |

## What changes in your project folder

- Generated files moved into `data/`: `candidates.json`, `results.json`, `run_status.json`, `seen.json`.
  An existing `seen.json` next to `config.json` is picked up automatically the first time, so nothing is re-sent.
- `cv.md`, `preferences.md`, `.env` and `config.json` stay where they are.
- Delete the old scripts, `common.py`, `skills/` and `run_pipeline.sh` (nothing uses them any more).
- `run_status.json` now says `sources_total` / `sources_ok` instead of `companies_total` / `companies_ok`.

## GitHub Actions

Replace `.github/workflows/job-hunter.yml` with the new one. It runs the `python -m jobhunter ...` commands and
commits `data/seen.json` (instead of `seen.json`). Make sure `data/seen.json` is not ignored (the new `.gitignore`
allows it); if you committed the old root `seen.json`, you can delete it after the first successful run.

## New optional settings

`profile.target_roles`, `scoring_weights`, `filters.location_require_terms`, `limits.fetch_workers`, and board options
such as `boards.remotive.category`. Defaults reproduce the old behaviour, except that the AI's role gate now uses
`profile.target_roles` (default: a generic phrase) instead of the fixed text "frontend or full-stack JavaScript".
Set it to describe your target roles.
