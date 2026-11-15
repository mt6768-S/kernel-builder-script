"""
KernelSU integration manager for kbuild.
Handles setup script download, owner extraction, injection, .config patching, and cleanup.
"""

from __future__ import annotations

import pathlib
import re
import subprocess

import requests
from loguru import logger

from kbuild.errors import IntegrationError


def extract_ksu_owner(setup_url: str) -> str:
    """
    Extracts the repository owner from the KernelSU setup script URL.
    Returns owner name, or 'OK' fallback if unparseable.
    """
    if not setup_url:
        return "OK"
    # Matches github.com/<owner>/... or raw.githubusercontent.com/<owner>/...
    m = re.search(r"(?:raw\.githubusercontent\.com|github\.com)/([^/]+)/", setup_url)
    if m:
        return m.group(1)
    return "OK"


class KernelSUManager:
    def __init__(
        self, source_dir: pathlib.Path, setup_url: str, target: str = "master"
    ):
        self.source_dir = source_dir
        self.setup_url = setup_url
        self.target = target or "master"
        self.injected = False

    def inject(self) -> None:
        logger.log(
            "STEP",
            "{}",
            f"[KSU] Injecting KernelSU ({self.target}) from {self.setup_url}",
        )

        try:
            resp = requests.get(
                self.setup_url, headers={"User-Agent": "kbuild"}, timeout=15
            )
            resp.raise_for_status()
            script_text = resp.text
        except Exception as e:
            raise IntegrationError(
                f"Failed to fetch KernelSU setup script from {self.setup_url}: {e}"
            )

        res = subprocess.run(
            ["bash", "-s", self.target],
            input=script_text,
            cwd=self.source_dir,
            capture_output=True,
            text=True,
        )

        if res.stdout:
            for line in res.stdout.splitlines():
                logger.info("{}", f"[KSU] {line}")

        if res.returncode != 0:
            err = res.stderr.strip() or res.stdout.strip()
            raise IntegrationError(
                f"KernelSU injection failed (code {res.returncode}): {err}"
            )

        self.injected = True
        logger.success("{}", "KernelSU setup script executed successfully.")

        # Update out/.config if it exists
        defconfig_path = self.source_dir / "out" / ".config"
        if defconfig_path.is_file():
            self._apply_ksu_config(defconfig_path)

    def _apply_ksu_config(self, defconfig_path: pathlib.Path) -> None:
        ksu_configs = {
            "CONFIG_KSU": "y",
            "CONFIG_KSU_EXTRAS": "y",
            "CONFIG_KSU_TAMPER_SYSCALL_TABLE": "y",
            "CONFIG_KSU_THRONE_TRACKER_ALWAYS_THREADED": "y",
        }

        try:
            with open(defconfig_path, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            new_lines = []
            found_keys = set()

            for line in lines:
                replaced = False
                for k, v in ksu_configs.items():
                    if line.startswith(f"{k}=") or line.startswith(f"# {k} is not set"):
                        new_lines.append(f"{k}={v}\n")
                        found_keys.add(k)
                        replaced = True
                        break
                if not replaced:
                    new_lines.append(line)

            for k, v in ksu_configs.items():
                if k not in found_keys:
                    new_lines.append(f"{k}={v}\n")

            with open(defconfig_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)

            logger.success("{}", "KernelSU configuration flags written to out/.config")
        except Exception as e:
            logger.warning(
                "{}", f"Failed to write KernelSU config flags to {defconfig_path}: {e}"
            )

    def cleanup(self) -> None:
        logger.info("{}", f"Cleaning up KernelSU in {self.source_dir}...")
        try:
            resp = requests.get(
                self.setup_url, headers={"User-Agent": "kbuild"}, timeout=15
            )
            if resp.status_code == 200:
                subprocess.run(
                    ["bash", "-s", "--", "--cleanup"],
                    input=resp.text,
                    cwd=self.source_dir,
                    capture_output=True,
                    text=True,
                )
                logger.success("{}", "KernelSU cleanup finished.")
        except Exception as e:
            logger.warning("{}", f"KernelSU cleanup error: {e}")
        finally:
            self.injected = False
