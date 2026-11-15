"""
Neutron Clang toolchain manager for kbuild.
Detects, downloads, extracts, validates, and manages toolchains in ~/.kbuild/clang.
"""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import shutil
import subprocess
from typing import Any

import requests
from loguru import logger

from kbuild.errors import ToolchainError
from kbuild.net import download_file
from kbuild.paths import (
    KBUILD_CLANG_DIR,
    KBUILD_ENV_FILE,
    KBUILD_ROOT,
    KBUILD_TOOLCHAIN_INFO_FILE,
    ensure_kbuild_dirs,
)


class ToolchainManager:
    REPO = "Neutron-Toolchains/clang-build-catalogue"
    LATEST_API_URL = "https://api.github.com/repos/Neutron-Toolchains/clang-build-catalogue/releases/latest"
    LATEST_PAGE_URL = (
        "https://github.com/Neutron-Toolchains/clang-build-catalogue/releases/latest"
    )

    @classmethod
    def test_clang_binary(cls, clang_bin: pathlib.Path) -> tuple[bool, str]:
        if not clang_bin.is_file():
            return False, "Binary not found"
        if not os.access(clang_bin, os.X_OK):
            return False, "Binary not executable"
        try:
            res = subprocess.run(
                [str(clang_bin), "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode == 0 and res.stdout:
                return True, res.stdout.splitlines()[0].strip()
            elif res.returncode in (-4, 132):
                return (
                    False,
                    "Incompatible with host CPU (Illegal instruction / missing AVX support)",
                )
            return False, f"Exit code {res.returncode}"
        except Exception as e:
            return False, str(e)

    @classmethod
    def get_latest_release_info(cls) -> dict[str, Any]:
        logger.info("{}", "Checking latest Neutron Clang release on GitHub...")
        tag_name: str | None = None
        asset_url: str | None = None
        asset_name: str | None = None
        published_at: str | None = None
        asset_size: int = 0

        # 1. GitHub API
        try:
            resp = requests.get(
                cls.LATEST_API_URL,
                headers={
                    "User-Agent": "kbuild-toolchain",
                    "Accept": "application/vnd.github.v3+json",
                },
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                tag_name = data.get("tag_name")
                published_at = data.get("published_at")
                for asset in data.get("assets", []):
                    name = asset.get("name", "")
                    if name.endswith((".tar.zst", ".tar.gz", ".tar.xz")):
                        asset_name = name
                        asset_url = asset.get("browser_download_url")
                        asset_size = asset.get("size", 0)
                        break
        except Exception as e:
            logger.warning("{}", f"GitHub API check failed ({e}), checking redirect...")

        # 2. HTTP redirect fallback
        if not tag_name or not asset_url:
            try:
                resp = requests.head(
                    cls.LATEST_PAGE_URL, allow_redirects=True, timeout=10
                )
                final_url = resp.url
                m = re.search(r"/tag/([^/?#]+)", final_url)
                if m:
                    tag_name = m.group(1)
                    asset_name = f"neutron-clang-{tag_name}.tar.zst"
                    asset_url = f"https://github.com/{cls.REPO}/releases/download/{tag_name}/{asset_name}"
            except Exception as e:
                logger.warning("{}", f"Redirect check failed: {e}")

        if not tag_name or not asset_url or not asset_name:
            raise ToolchainError(
                "Could not determine latest Neutron Clang release from GitHub."
            )

        return {
            "tag": tag_name,
            "asset_name": asset_name,
            "download_url": asset_url,
            "published_at": published_at
            or datetime.datetime.now(datetime.UTC).isoformat(),
            "size": asset_size,
        }

    @classmethod
    def get_installed_info(cls) -> dict[str, Any] | None:
        if KBUILD_TOOLCHAIN_INFO_FILE.is_file():
            try:
                with open(KBUILD_TOOLCHAIN_INFO_FILE, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return None
        return None

    @classmethod
    def save_installed_info(cls, info: dict[str, Any]) -> None:
        ensure_kbuild_dirs()
        with open(KBUILD_TOOLCHAIN_INFO_FILE, "w", encoding="utf-8") as f:
            json.dump(info, f, indent=2)
            f.write("\n")

    @classmethod
    def write_env_file(cls, clang_dir: pathlib.Path) -> None:
        """Writes ~/.kbuild/bin/env.sh for shell sourcing."""
        ensure_kbuild_dirs()
        content = f"""# kbuild environment configuration
export KBUILD_DIR="{KBUILD_ROOT}"
export PATH="{clang_dir / "bin"}:$HOME/.local/bin:$HOME/.kbuild/bin:$PATH"
"""
        with open(KBUILD_ENV_FILE, "w", encoding="utf-8") as f:
            f.write(content)
        KBUILD_ENV_FILE.chmod(0o755)

    @classmethod
    def extract_archive(
        cls, archive_path: pathlib.Path, dest_dir: pathlib.Path
    ) -> None:
        """Extracts tarball to dest_dir."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        # Try standard tar subprocess with auto compression detection
        cmd = ["tar", "-xf", str(archive_path), "-C", str(dest_dir)]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            # Fallback with explicit --zstd
            cmd = ["tar", "--zstd", "-xf", str(archive_path), "-C", str(dest_dir)]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                raise ToolchainError(
                    f"Extraction failed: {res.stderr.strip() or res.stdout.strip()}"
                )

    @classmethod
    def ensure_clang(cls, force: bool = False) -> pathlib.Path:
        clang_bin = KBUILD_CLANG_DIR / "bin" / "clang"
        installed_info = cls.get_installed_info()

        if clang_bin.is_file() and not force:
            is_ok, ver = cls.test_clang_binary(clang_bin)
            if is_ok:
                tag = (
                    installed_info.get("tag", "custom") if installed_info else "unknown"
                )
                logger.info(
                    "{}", f"Using Neutron Clang at: {KBUILD_CLANG_DIR} (Tag: {tag})"
                )
                return KBUILD_CLANG_DIR

        rel_info = cls.get_latest_release_info()
        latest_tag = rel_info["tag"]

        if (
            clang_bin.is_file()
            and installed_info
            and installed_info.get("tag") == latest_tag
            and not force
        ):
            logger.info(
                "{}", f"Neutron Clang is already up-to-date (Tag: {latest_tag})"
            )
            return KBUILD_CLANG_DIR

        logger.log("STEP", "{}", f"[TOOLCHAIN] Installing Neutron Clang ({latest_tag})")
        archive_path = KBUILD_ROOT / rel_info["asset_name"]

        logger.info("{}", f"Downloading from: {rel_info['download_url']}")
        download_file(
            rel_info["download_url"], archive_path, description="Neutron Clang"
        )

        logger.info("{}", f"Extracting {archive_path.name} to {KBUILD_CLANG_DIR}...")
        if KBUILD_CLANG_DIR.exists():
            shutil.rmtree(KBUILD_CLANG_DIR, ignore_errors=True)
        KBUILD_CLANG_DIR.mkdir(parents=True, exist_ok=True)

        try:
            cls.extract_archive(archive_path, KBUILD_CLANG_DIR)
        finally:
            if archive_path.is_file():
                archive_path.unlink()

        # Test compatibility
        is_ok, ver_str = cls.test_clang_binary(clang_bin)

        metadata = {
            "name": "Neutron Clang",
            "tag": latest_tag,
            "installed_at": datetime.datetime.now(datetime.UTC).isoformat(),
            "download_url": rel_info["download_url"],
            "asset_name": rel_info["asset_name"],
            "version_string": ver_str,
            "compatible": is_ok,
            "path": str(KBUILD_CLANG_DIR),
        }
        cls.save_installed_info(metadata)
        cls.write_env_file(KBUILD_CLANG_DIR)

        if is_ok:
            logger.success(
                "{}",
                f"Neutron Clang ({latest_tag}) installed successfully at {KBUILD_CLANG_DIR}!",
            )
            logger.info("{}", f"Version: {ver_str}")
        else:
            logger.warning(
                "{}", f"Neutron Clang downloaded, but binary reported: {ver_str}"
            )

        return KBUILD_CLANG_DIR

    @classmethod
    def resolve_toolchain(cls, explicit_path: str | None = None) -> pathlib.Path | None:
        """Resolves toolchain directory, falling back to system clang if needed."""
        if explicit_path:
            p = pathlib.Path(explicit_path).expanduser().resolve()
            if (p / "bin" / "clang").is_file():
                return p
            raise ToolchainError(
                f"Specified toolchain directory does not contain bin/clang: {p}"
            )

        neutron_bin = KBUILD_CLANG_DIR / "bin" / "clang"
        if neutron_bin.is_file():
            is_ok, _ = cls.test_clang_binary(neutron_bin)
            if is_ok:
                return KBUILD_CLANG_DIR

        # Attempt to install or update Neutron Clang
        try:
            return cls.ensure_clang(force=False)
        except Exception as e:
            logger.warning("{}", f"Could not prepare Neutron Clang: {e}")

        # Check system clang fallback
        sys_clang = shutil.which("clang")
        if sys_clang:
            sys_path = pathlib.Path(sys_clang).resolve()
            is_ok, ver = cls.test_clang_binary(sys_path)
            if is_ok:
                logger.warning(
                    "{}", f"Falling back to system Clang: {ver} ({sys_clang})"
                )
                return sys_path.parent.parent

        raise ToolchainError(
            "No functional Clang toolchain found (Neutron Clang download failed and system clang not found)."
        )
