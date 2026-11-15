#!/usr/bin/env bash
# Uninstaller runner for kbuild
set -e

if [ -x "$HOME/.kbuild/venv/bin/kb" ]; then
    exec "$HOME/.kbuild/venv/bin/kb" uninstall "$@"
elif command -v kb >/dev/null 2>&1; then
    exec kb uninstall "$@"
else
    exec python3 -m kbuild uninstall "$@"
fi
