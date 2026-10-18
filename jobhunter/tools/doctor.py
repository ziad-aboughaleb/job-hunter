"""`doctor`: an offline checklist of your setup. Prints one line per check; returns 1 if anything needs fixing."""
import os

from jobhunter.helpers import paths, store
from jobhunter.helpers.config import load_config, load_env, validate


def run() -> int:
    load_env()
    problems = 0

    def report(ok: bool, text: str) -> None:
        nonlocal problems
        print(("  ok   " if ok else "  FIX  ") + text)
        problems += 0 if ok else 1

    config_exists = (paths.root() / "config.json").exists()
    report(config_exists, "config.json exists" + ("" if config_exists else " (run `python -m jobhunter init`)"))
    cfg = load_config(quiet=True)
    for warning in validate(cfg):
        report(False, f"config: {warning}")
    enabled_boards = sum(1 for b in cfg["boards"].values() if (b if isinstance(b, bool) else b.get("enabled", True)))
    sources = sum(len(v) for v in cfg["companies"].values()) + enabled_boards
    report(sources > 0, f"{sources} source(s) configured (boards + company names)")

    cv = store.read_text("cv.md")
    report(len(cv) >= 400 and not cv.lstrip().startswith("<!--"), "cv.md contains your CV")
    preferences = store.read_text("preferences.md")
    report(bool(preferences) and "<FILL IN" not in preferences, "preferences.md is filled in (no <FILL IN> left)")

    report(bool(os.environ.get("TELEGRAM_BOT_TOKEN")), "TELEGRAM_BOT_TOKEN is set")
    report(bool(os.environ.get("TELEGRAM_CHAT_ID")), "TELEGRAM_CHAT_ID is set")
    if cfg["llm"]["provider"] == "openai":
        key = cfg["llm"]["api_key_env"]
        report(bool(os.environ.get(key)), f"{key} is set (the AI API key)")
    else:
        print("  --   llm.provider is 'ollama': make sure `ollama serve` is running and the model is pulled")

    print("\nAll good." if not problems else f"\n{problems} thing(s) to fix.")
    return 1 if problems else 0
