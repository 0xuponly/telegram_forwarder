#!/bin/bash
# UI needs Flask; Homebrew Python blocks global pip — use .venv
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt
exec .venv/bin/python ui_app.py
