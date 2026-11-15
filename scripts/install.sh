#!/usr/bin/env bash
# Bootstrap installer for kbuild
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Verify Python version >= 3.12
PYTHON=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c "import sys; exit(0 if sys.version_info >= (3, 12) else 1)" 2>/dev/null; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "Error: Python 3.12 or newer is required to install kbuild." >&2
    exit 1
fi

exec "$PYTHON" -m kbuild.install "$@"
