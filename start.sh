#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
# Homebrew (often used on Bazzite) may be missing from KDE launcher PATH.
export PATH="/home/linuxbrew/.linuxbrew/bin:$HOME/.linuxbrew/bin:$PATH"
if ! command -v git >/dev/null 2>&1; then
  echo 'Git is missing. Please install git first.' >&2
  exit 1
fi
if [ ! -x .venv/bin/python ]; then
  echo 'First run: creating the Python Qt6 environment...'
  python3 -m venv .venv
fi
if ! .venv/bin/python -c 'import PySide6' 2>/dev/null; then
  echo 'First run: installing PySide6...'
  .venv/bin/python -m pip install -r requirements.txt
fi
exec .venv/bin/python app.py
