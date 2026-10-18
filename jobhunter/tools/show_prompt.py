"""`prompt`: print the exact instructions the AI receives, built from YOUR config.json, CV and preferences.

Use it to see which parts of the rubric come from your settings, and to check your edits took effect.
"""
from jobhunter.evaluate.prompt import build_system_prompt, build_user_message
from jobhunter.helpers import store
from jobhunter.helpers.config import load_config

CV_PLACEHOLDER = "<<< the text of cv.md goes here >>>"
PREFERENCES_PLACEHOLDER = "<<< the text of preferences.md goes here >>>"


def run(hide_cv: bool = False) -> int:
    cfg = load_config()
    cv, preferences = store.read_text("cv.md"), store.read_text("preferences.md")
    if hide_cv or not cv:
        cv = CV_PLACEHOLDER
    if hide_cv or not preferences:
        preferences = PREFERENCES_PLACEHOLDER

    prompt = build_system_prompt(cfg, cv, preferences)
    print("=" * 70)
    print("SYSTEM PROMPT (sent with every job; the CV and preferences come last so servers can cache the start)")
    print("=" * 70)
    print(prompt)

    candidates = store.read_data("candidates.json", None) or []
    if candidates:
        print("=" * 70)
        print(f"USER MESSAGE (this part changes per job; shown for the first candidate, {candidates[0]['ref']})")
        print("=" * 70)
        print(build_user_message(candidates[0], cfg["limits"]["description_max_chars"]))
    print(f"\n[{len(prompt)} characters in the system prompt, roughly {len(prompt) // 3} tokens]")
    return 0
