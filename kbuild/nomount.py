"""
NoMount integration manager for kbuild.
Handles setup script download, injection, .config patching, and cleanup.
"""

from __future__ import annotations

import pathlib
import subprocess

import requests

from kbuild.console import log_info, log_step, log_success, log_warn
from kbuild.errors import IntegrationError


class NoMountManager:
    def __init__(self, source_dir: pathlib.Path, setup_url: str, target: str = "dev"):
        self.source_dir = source_dir
        self.setup_url = setup_url
        self.target = target or "dev"
        self.injected = False

    def inject(self) -> None:
        log_step("NOMOUNT", f"Injecting NoMount ({self.target}) from {self.setup_url}")

        try:
            resp = requests.get(
                self.setup_url, headers={"User-Agent": "kbuild"}, timeout=15
            )
            resp.raise_for_status()
            script_text = resp.text
        except Exception as e:
            raise IntegrationError(
                f"Failed to fetch NoMount setup script from {self.setup_url}: {e}"
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
                log_info(f"[NOMOUNT] {line}")

        if res.returncode != 0:
            err = res.stderr.strip() or res.stdout.strip()
            raise IntegrationError(
                f"NoMount injection failed (code {res.returncode}): {err}"
            )

        self.injected = True
        log_success("NoMount setup script executed successfully.")

        # Update out/.config if it exists
        defconfig_path = self.source_dir / "out" / ".config"
        if defconfig_path.is_file():
            self._apply_nomount_config(defconfig_path)

    def _apply_nomount_config(self, defconfig_path: pathlib.Path) -> None:
        nomount_configs = {
            "CONFIG_NOMOUNT": "y",
        }

        try:
            with open(defconfig_path, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            new_lines = []
            found_keys = set()

            for line in lines:
                replaced = False
                for k, v in nomount_configs.items():
                    if line.startswith((f"{k}=", f"# {k} is not set")):
                        new_lines.append(f"{k}={v}\n")
                        found_keys.add(k)
                        replaced = True
                        break
                if not replaced:
                    new_lines.append(line)

            for k, v in nomount_configs.items():
                if k not in found_keys:
                    new_lines.append(f"{k}={v}\n")

            with open(defconfig_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)

            log_success("NoMount configuration flags written to out/.config")
        except Exception as e:
            log_warn(f"Failed to write NoMount config flags to {defconfig_path}: {e}")

    def cleanup(self) -> None:
        log_info(f"Cleaning up NoMount in {self.source_dir}...")
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
                log_success("NoMount cleanup finished.")
        except Exception as e:
            log_warn(f"NoMount cleanup error: {e}")
        finally:
            self.injected = False
