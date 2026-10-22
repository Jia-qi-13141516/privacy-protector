#!/bin/sh
cd -- "$(dirname -- "$0")" || exit 1
if command -v codex >/dev/null 2>&1; then
  exec python3 -B scripts/auto_setup.py --agent codex
elif command -v claude >/dev/null 2>&1; then
  exec python3 -B scripts/auto_setup.py --agent claude
else
  echo 'Mac 版需要 Codex 或 Claude Code 命令行客户端。请让本地 Agent 根据 SKILL.md 完成安装。'
  exit 2
fi
