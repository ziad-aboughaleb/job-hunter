"""Job Hunter: fetch remote tech jobs, score them against your CV with an LLM, get the matches on Telegram.

How the package is organised (each folder has a short README-style docstring in its __init__.py):

    cli.py       the command line: `python -m jobhunter <command>`
    helpers/     shared building blocks: files, HTTP, text, config, the Job type
    fetch/       STAGE 1: get jobs from many sites and filter them        (sources/, filters.py, stage.py)
    evaluate/    STAGE 2: score each job against your CV with an AI       (prompt.py, llm.py, parsing.py, stage.py)
    send/        STAGE 3: send the matches to Telegram, remember progress (matches.py, telegram.py, stage.py)
    tools/       maintenance commands: init, doctor, prompt, discover, prune

Every stage folder has a `stage.py` with a `run()` function: that is the stage's entry point, start reading there.
"""

__version__ = "3.1.0"
