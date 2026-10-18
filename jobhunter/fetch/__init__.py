"""STAGE 1 - get jobs and filter them.  Entry point: stage.py -> run()

    sources/     one small file per job site (Greenhouse, Lever, Remotive, ...). Add a site here.
    filters.py   the rules that decide which jobs are worth showing to the AI
    stage.py     glue: fetch every source, apply the rules, rank, write data/candidates.json
"""
