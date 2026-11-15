#!/usr/bin/env bash
# Bootstrap installer for kbuild (supports curl -sSL ... | bash)
set -e

REPO_URL="https://github.com/mt6768-S/kernel-builder-script.git"
KBUILD_ROOT="${KBUILD_DIR:-$HOME/.kbuild}"
APP_DIR="$KBUILD_ROOT/app"
VENV_DIR="$KBUILD_ROOT/venv"

# 1. Locate Python >= 3.12
PYTHON=""
for candidate in python3 python python3.14 python3.13 python3.12; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c "import sys; exit(0 if sys.version_info >= (3, 12) else 1)" 2>/dev/null; then
            PYTHON="$(command -v "$candidate")"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "Error: Python 3.12 or newer is required to install kbuild." >&2
    exit 1
fi

mkdir -p "$KBUILD_ROOT"

# 2. Check if running from a local git repository or piped via curl
SCRIPT_DIR=""
if [ -n "${BASH_SOURCE[0]}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)"
fi

if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/pyproject.toml" ]; then
    SOURCE_DIR="$SCRIPT_DIR"
    if [ "$SOURCE_DIR" != "$APP_DIR" ]; then
        mkdir -p "$APP_DIR"
        echo "[*] Syncing kbuild repository to $APP_DIR..."
        if command -v rsync >/dev/null 2>&1; then
            rsync -a --delete --exclude=".git" --exclude="__pycache__" --exclude=".pytest_cache" --exclude="venv" "$SOURCE_DIR/" "$APP_DIR/"
        else
            cp -r "$SOURCE_DIR"/* "$APP_DIR/" 2>/dev/null || true
        fi
        if [ -d "$SOURCE_DIR/.git" ]; then
            rm -rf "$APP_DIR/.git"
            cp -r "$SOURCE_DIR/.git" "$APP_DIR/.git" 2>/dev/null || true
        fi
    fi
else
    # Piped execution (e.g. curl -sSL ... | bash)
    if [ ! -d "$APP_DIR/.git" ]; then
        echo "[*] Cloning kbuild repository into $APP_DIR..."
        rm -rf "$APP_DIR"
        git clone "$REPO_URL" "$APP_DIR"
    else
        echo "[*] Updating existing kbuild repository in $APP_DIR..."
        git -C "$APP_DIR" pull --ff-only || true
    fi
fi

# 3. Create virtual environment using system Python if it doesn't exist
if [ ! -f "$VENV_DIR/bin/python" ] || [ ! -f "$VENV_DIR/bin/pip" ]; then
    echo "[*] Creating virtual environment at $VENV_DIR..."
    rm -rf "$VENV_DIR"
    if ! "$PYTHON" -m venv "$VENV_DIR"; then
        if command -v virtualenv >/dev/null 2>&1; then
            virtualenv -p "$PYTHON" "$VENV_DIR"
        else
            echo "Error: Failed to create Python virtual environment." >&2
            echo "Please ensure python3-venv is installed (e.g. 'sudo apt install python3-venv')." >&2
            exit 1
        fi
    fi
fi

# 4. Install kbuild and its dependencies into the virtual environment
echo "[*] Installing kbuild and dependencies into virtual environment..."
"$VENV_DIR/bin/pip" install --upgrade pip --quiet
"$VENV_DIR/bin/pip" install -e "$APP_DIR" --quiet

# 5. Complete setup (symlinks, shell hooks, default config) via venv Python
exec "$VENV_DIR/bin/python" -m kbuild.install "$@"
