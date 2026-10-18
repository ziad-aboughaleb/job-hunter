"""STAGE 2 - score each candidate job against your CV with an AI.  Entry point: stage.py -> run()

    prompt.py    builds the AI's instructions (the rubric) from config.json + your CV + preferences.md
    llm.py       talks to the model: Ollama, or any OpenAI-compatible API such as Gemini
    parsing.py   repairs and validates the model's reply
    stage.py     the loop: one independent request per job, results saved after every job
"""
