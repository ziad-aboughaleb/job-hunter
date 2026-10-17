#!/usr/bin/env bash
# Runs the whole pipeline: fetch -> evaluate -> Telegram.
cd "$(dirname "$0")" || exit 1
mkdir -p logs
{
  echo "=== $(date -Is) ==="
  python3 fetch_jobs.py "$@"
  python3 evaluate_jobs.py
  python3 send_telegram.py
} >>"logs/$(date +%F).log" 2>&1
