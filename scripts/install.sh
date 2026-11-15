#!/usr/bin/env bash
# Bootstrap installer for kbuild (supports curl ... | bash)
set -e

REPO_URL="https://github.com/mt6768-S/kernel-builder-script.git"
KBUILD_ROOT="${KBUILD_DIR:-$HOME/.kbuild}"
APP_DIR="$KBUILD_ROOT/app"

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

mkdir -p "$KBUILD_ROOT"

# Check if running from a local git clone
SCRIPT_DIR=""
if [ -n "${BASH_SOURCE[0]}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)"
fi

if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/pyproject.toml" ]; then
    PYTHONPATH="$SCRIPT_DIR" exec "$PYTHON" -m kbuild.install "$@"
fi

# Piped execution (e.g. curl -sSL ... | bash): clone or update into ~/.kbuild/app
if [ ! -d "$APP_DIR/.git" ]; then
    echo "[*] Cloning kbuild repository into $APP_DIR..."
    rm -rf "$APP_DIR"
    git clone "$REPO_URL" "$APP_DIR"
else
    echo "[*] Updating existing kbuild repository in $APP_DIR..."
    git -C "$APP_DIR" pull --ff-only || true
fi

PYTHONPATH="$APP_DIR" exec "$PYTHON" -m kbuild.install "$@"
