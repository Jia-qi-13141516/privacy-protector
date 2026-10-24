#!/bin/sh
cd -- "$(dirname -- "$0")" || exit 1
if command -v codex >/dev/null 2>&1; then
  exec python3 -B scripts/auto_setup.py --agent codex
elif command -v claude >/dev/null 2>&1; then
  exec python3 -B scripts/auto_setup.py --agent claude
else
  exec python3 -B scripts/auto_setup.py --agent workbuddy
fi
