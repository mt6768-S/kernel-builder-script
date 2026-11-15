#!/usr/bin/env bash
# Update runner for kbuild
set -e

if [ -x "$HOME/.kbuild/venv/bin/kb" ]; then
    exec "$HOME/.kbuild/venv/bin/kb" update "$@"
elif command -v kb >/dev/null 2>&1; then
    exec kb update "$@"
else
    exec python3 -m kbuild update "$@"
fi
