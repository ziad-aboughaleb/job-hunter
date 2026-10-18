"""Shared building blocks used by every stage. Nothing here knows about job hunting rules.

    paths.py     where files live (project folder, data/)
    store.py     reading and writing JSON files safely; the seen.json helpers
    http.py      GET/POST with retries (standard library only)
    textutil.py  HTML to text, date parsing, whole-word matching
    config.py    defaults, loading config.json, warnings about mistakes, .env
    models.py    the Job type that every source produces and every later stage consumes
"""
