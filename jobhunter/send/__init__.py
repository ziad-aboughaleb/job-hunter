"""STAGE 3 - deliver the matches and remember what is finished.  Entry point: stage.py -> run()

    matches.py   validate results.json, pick the matches, decide which jobs are "seen" (finished)
    telegram.py  format a job as a message (with escaping) and send it
    stage.py     glue: send the cards and a summary, then update data/seen.json
"""
