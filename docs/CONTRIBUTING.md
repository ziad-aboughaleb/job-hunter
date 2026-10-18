# Contributing

Thanks for helping! This project is deliberately small and dependency-free, so changes are easy to review.

## Setup

```bash
git clone <repo> && cd job-hunter
python -m unittest discover -s tests -t .      # should print OK
```

No packages to install. Python 3.8+ is supported, so avoid newer syntax (no `match`, no `X | Y` type unions, no
`list[str]` generics). CI runs the tests on 3.8 and 3.12.

## Ground rules

- **Standard library only** for the daily run. Optional tools may use an optional package (see `discover`).
- **No network in tests.** Fake `jobhunter.http` functions; see `tests/support.py` and the existing tests.
- **Small modules, plain functions, docstrings that say _why_.** Someone should be able to read a file top to bottom.
- **Never trust text from the internet or the model:** escape it for Telegram, validate model output, treat job text as data.
- **Never lose a job:** keep the "seen means finished" rule in `jobhunter/send/matches.py` intact.
- **Don't add personal data** (CVs, tokens, your own config) to the repo.

## Where things go

Tests mirror the code: `jobhunter/fetch/filters.py` is tested in `tests/fetch/test_filters.py`. Shared test setup is in
`tests/support.py`.

## Adding a job site

It is one small file plus a test. See "Add a job site" in [ARCHITECTURE.md](ARCHITECTURE.md). A fixture in the test should be a trimmed
copy of the site's real response.

## Pull requests

1. Add or update tests for the change; keep the suite green.
2. Update [CONFIG.md](CONFIG.md) if you added or changed a setting (and the defaults in `jobhunter/helpers/config.py`).
3. Describe what changed and why in the PR. Screenshots/log excerpts help for behaviour changes.

## Reporting problems

Include the command you ran, the output (with secrets removed), and `data/run_status.json` if it concerns fetching.
