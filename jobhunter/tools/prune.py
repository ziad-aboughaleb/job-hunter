"""Remove company boards that returned 404 ("board not found") in the last fetch from config.json.

Reads data/run_status.json, so run `fetch` first. Only 404s are removed, never network failures.
"""
from jobhunter.helpers import paths, store


def run(dry_run: bool = False) -> int:
    status = store.read_data("run_status.json", None)
    if not status:
        print("data/run_status.json not found: run `python -m jobhunter fetch` first.")
        return 1
    config_path = paths.root() / "config.json"
    cfg = store.read_json(config_path, {})

    removed = []
    for error in status.get("errors", []):
        if "board not found" not in error:
            continue
        source, name = error.split(":", 1)[0].split("/", 1)
        names = cfg.get("companies", {}).get(source, [])
        kept = [n for n in names if n.strip().lower() != name.strip().lower()]
        if len(kept) != len(names):
            cfg["companies"][source] = kept
            removed.append(f"{source}/{name}")

    print(f"{'Would remove' if dry_run else 'Removed'} {len(removed)} board(s):")
    for item in removed:
        print("  -", item)
    if removed and not dry_run:
        store.write_json(config_path, cfg)
        print("config.json updated.")
    return 0
