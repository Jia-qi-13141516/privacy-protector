#!/bin/sh
cd -- "$(dirname -- "$0")" || exit 1
exec python3 scripts/auto_setup.py --agent codex
