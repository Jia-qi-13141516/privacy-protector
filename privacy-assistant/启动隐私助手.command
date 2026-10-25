#!/bin/sh
cd -- "$(dirname -- "$0")" || exit 1
case "$(uname -m)" in
  arm64) python="runtime-macos-arm64/bin/python3" ;;
  x86_64) python="runtime-macos-x86_64/bin/python3" ;;
  *) exit 2 ;;
esac
if command -v codex >/dev/null 2>&1; then
  exec "$python" -I -B scripts/auto_setup.py --agent codex
elif command -v claude >/dev/null 2>&1; then
  exec "$python" -I -B scripts/auto_setup.py --agent claude
else
  exec "$python" -I -B scripts/auto_setup.py --agent workbuddy
fi
