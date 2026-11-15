"""
Update checker and updater for kbuild.
Throttles automated update checks to once per 24 hours and provides 'kb update'.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import time

from loguru import logger

from kbuild import __version__, console
from kbuild.paths import (
    KBUILD_APP_DIR,
    KBUILD_UPDATE_CACHE_FILE,
    KBUILD_VENV_DIR,
    ensure_kbuild_dirs,
)

CHECK_INTERVAL_SECONDS = 86400  # 24 hours
REPO_API_URL = (
    "https://api.github.com/repos/mt6768-S/kernel-builder-script/releases/latest"
)
REPO_COMMITS_URL = (
    "https://api.github.com/repos/mt6768-S/kernel-builder-script/commits/main"
)


def should_check_update() -> bool:
    if not KBUILD_UPDATE_CACHE_FILE.is_file():
        return True
    try:
        with open(KBUILD_UPDATE_CACHE_FILE, encoding="utf-8") as f:
            data = json.load(f)
            last_checked = data.get("last_checked", 0)
            return (time.time() - last_checked) > CHECK_INTERVAL_SECONDS
    except Exception:
        return True


def save_update_cache(latest_version: str | None, notice: str | None) -> None:
    ensure_kbuild_dirs()
    try:
        payload = {
            "last_checked": time.time(),
            "latest_version": latest_version,
            "notice": notice,
        }
        with open(KBUILD_UPDATE_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f)
    except Exception:
        pass


def check_for_updates(
    quiet: bool = True, force: bool = False
) -> tuple[bool, str | None]:
    """
    Checks for available updates against GitHub repository.
    Returns (has_update, message).
    """
    if not force and not should_check_update():
        # Read cached notice if present
        try:
            with open(KBUILD_UPDATE_CACHE_FILE, encoding="utf-8") as f:
                data = json.load(f)
                notice = data.get("notice")
                if notice:
                    return True, notice
        except Exception:
            pass
        return False, None

    import requests

    latest_tag = None
    notice = None

    try:
        resp = requests.get(
            REPO_API_URL,
            headers={
                "User-Agent": "kbuild-updater",
                "Accept": "application/vnd.github.v3+json",
            },
            timeout=2.5,
        )
        if resp.status_code == 200:
            data = resp.json()
            latest_tag = data.get("tag_name", "").lstrip("v")
    except Exception:
        pass

    if latest_tag:
        try:
            from packaging import version

            if version.parse(latest_tag) > version.parse(__version__):
                notice = f"A new version of kbuild is available: {__version__} -> {latest_tag}. Run 'kb update' to upgrade."
        except Exception:
            if latest_tag != __version__:
                notice = f"A new version of kbuild is available: {latest_tag}. Run 'kb update' to upgrade."

    save_update_cache(latest_tag, notice)
    return bool(notice), notice


def notify_if_update_available() -> None:
    """Non-blocking hook called by CLI to show update notice if available."""
    try:
        has_update, message = check_for_updates(quiet=True, force=False)
        if has_update and message:
            console.print(f"\n[bold yellow][Notice] {message}[/bold yellow]\n")
    except Exception:
        pass


def perform_update() -> bool:
    """
    Performs 'kb update':
    1. Runs git pull on installed repo (or current repo)
    2. Synchronizes dependencies in ~/.kbuild/venv
    """
    target_repo = (
        KBUILD_APP_DIR if (KBUILD_APP_DIR / ".git").is_dir() else pathlib.Path.cwd()
    )
    if not (target_repo / ".git").is_dir():
        logger.error("{}", f"Cannot update: {target_repo} is not a git repository.")
        return False

    logger.info("{}", f"Updating kbuild in {target_repo}...")
    try:
        pull_res = subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=target_repo,
            capture_output=True,
            text=True,
        )
        if pull_res.returncode != 0:
            logger.error(
                "{}",
                f"Git pull failed: {pull_res.stderr.strip() or pull_res.stdout.strip()}",
            )
            return False
        logger.success("{}", "Git repository updated successfully.")
        print(pull_res.stdout.strip())
    except Exception as e:
        logger.error("{}", f"Failed to execute git pull: {e}")
        return False

    # Sync venv if ~/.kbuild/venv exists
    pip_bin = KBUILD_VENV_DIR / "bin" / "pip"
    if pip_bin.is_file():
        logger.info("{}", f"Syncing virtual environment at {KBUILD_VENV_DIR}...")
        try:
            pip_res = subprocess.run(
                [str(pip_bin), "install", "-e", str(target_repo)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if pip_res.returncode == 0:
                logger.success("{}", "kbuild dependencies synchronized successfully.")
            else:
                logger.warning(
                    "{}",
                    f"pip install returned code {pip_res.returncode}: {pip_res.stderr.strip()}",
                )
        except Exception as e:
            logger.warning("{}", f"Failed to sync virtual environment: {e}")

    # Invalidate update cache after update
    if KBUILD_UPDATE_CACHE_FILE.is_file():
        KBUILD_UPDATE_CACHE_FILE.unlink()

    return True
