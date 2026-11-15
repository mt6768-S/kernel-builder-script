"""
Path definitions and directory helpers for kbuild.
All persistent state lives in ~/.kbuild.
"""

from __future__ import annotations

import os
import pathlib


def get_kbuild_root() -> pathlib.Path:
    custom = os.environ.get("KBUILD_DIR")
    if custom:
        return pathlib.Path(custom).expanduser().resolve()
    return (pathlib.Path.home() / ".kbuild").resolve()


KBUILD_ROOT = get_kbuild_root()
KBUILD_BIN_DIR = KBUILD_ROOT / "bin"
KBUILD_APP_DIR = KBUILD_ROOT / "app"
KBUILD_VENV_DIR = KBUILD_ROOT / "venv"
KBUILD_CLANG_DIR = KBUILD_ROOT / "clang"
KBUILD_AK3_DIR = KBUILD_ROOT / "AnyKernel3"
KBUILD_CACHE_DIR = KBUILD_ROOT / "cache"

KBUILD_CONFIG_FILE = KBUILD_ROOT / "config.json"
KBUILD_TOOLCHAIN_INFO_FILE = KBUILD_ROOT / "toolchain_info.json"
KBUILD_ENV_FILE = KBUILD_BIN_DIR / "env.sh"
KBUILD_UPDATE_CACHE_FILE = KBUILD_CACHE_DIR / "update_check.json"

LOCAL_CONFIG_NAMES = (".kb.json", "kb.json", ".pb.json", "pb.json")


def ensure_kbuild_dirs() -> None:
    """Creates the standard ~/.kbuild directory hierarchy."""
    for d in (
        KBUILD_ROOT,
        KBUILD_BIN_DIR,
        KBUILD_CLANG_DIR,
        KBUILD_AK3_DIR,
        KBUILD_CACHE_DIR,
    ):
        d.mkdir(parents=True, exist_ok=True)


def find_local_config(cwd: pathlib.Path | None = None) -> pathlib.Path | None:
    """Finds project-local configuration file if present in cwd."""
    base = cwd or pathlib.Path.cwd()
    for name in LOCAL_CONFIG_NAMES:
        candidate = base / name
        if candidate.is_file():
            return candidate
    return None


def get_symlink_path() -> pathlib.Path:
    """Returns ~/.local/bin/kb symlink path."""
    return (pathlib.Path.home() / ".local" / "bin" / "kb").resolve()
