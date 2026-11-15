"""
AnyKernel3 manager and zip packaging module for kbuild.
Uses Python's zipfile module for deterministic archive creation in /tmp.
"""

from __future__ import annotations

import datetime
import hashlib
import os
import pathlib
import shutil
import subprocess
import tempfile
import zipfile
from collections.abc import Sequence

from loguru import logger

from kbuild.config import KbuildConfig
from kbuild.errors import PackagingError
from kbuild.paths import KBUILD_AK3_DIR, ensure_kbuild_dirs


class AnyKernelManager:
    def __init__(self, config: KbuildConfig):
        self.config = config
        self.ak3_dir = KBUILD_AK3_DIR

    def ensure_ak3(self, explicit_path_or_repo: str | None = None) -> pathlib.Path:
        if explicit_path_or_repo:
            p = pathlib.Path(explicit_path_or_repo).expanduser().resolve()
            if (p / "anykernel.sh").is_file():
                logger.info("{}", f"Using explicit AnyKernel3 path: {p}")
                return p

        ensure_kbuild_dirs()
        ak3_script = self.ak3_dir / "anykernel.sh"

        if not ak3_script.is_file():
            repo_url = (
                explicit_path_or_repo
                if (explicit_path_or_repo and "://" in explicit_path_or_repo)
                else self.config.ak3_repo
            )
            logger.log("STEP", "{}", f"[AK3] Cloning AnyKernel3 from {repo_url}...")
            res = subprocess.run(
                ["git", "clone", "--depth=1", repo_url, str(self.ak3_dir)],
                capture_output=True,
                text=True,
            )
            if res.returncode != 0:
                raise PackagingError(
                    f"Failed to clone AnyKernel3: {res.stderr.strip() or res.stdout.strip()}"
                )
            logger.success("{}", f"AnyKernel3 cloned to {self.ak3_dir}")
        else:
            logger.info("{}", f"Updating cached AnyKernel3 at {self.ak3_dir}...")
            try:
                res = subprocess.run(
                    ["git", "pull", "--ff-only"],
                    cwd=self.ak3_dir,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if res.returncode == 0:
                    logger.success("{}", "AnyKernel3 cache updated.")
                else:
                    logger.warning(
                        "{}",
                        f"AnyKernel3 git pull failed; using cached files: {res.stderr.strip()}",
                    )
            except Exception as e:
                logger.warning(
                    "{}", f"AnyKernel3 update failed ({e}); using cached files."
                )

        if not ak3_script.is_file():
            raise PackagingError(
                f"AnyKernel3 cache is missing anykernel.sh in {self.ak3_dir}"
            )

        return self.ak3_dir

    def package(
        self,
        artifacts: Sequence[pathlib.Path],
        device: str,
        prefix: str = "Skyron",
        explicit_ak3: str | None = None,
    ) -> tuple[pathlib.Path, str]:
        """
        Creates an AnyKernel3 flashable zip in /tmp with format:
        /tmp/{prefix}-{device}-{YYYYMMDDHHMM}.zip
        Returns (zip_path, sha256_hex).
        """
        ak3_source = self.ensure_ak3(explicit_ak3)
        valid_artifacts = [p for p in artifacts if p and p.is_file()]
        if not valid_artifacts:
            raise PackagingError("No compiled kernel artifacts found to package.")

        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M")
        zip_name = f"{prefix}-{device}-{timestamp}.zip"
        zip_path = pathlib.Path("/tmp") / zip_name

        logger.log(
            "STEP",
            "{}",
            f"[PACKAGE] Creating flashable AnyKernel3 zip: {zip_path.name}",
        )

        with tempfile.TemporaryDirectory(prefix="kbuild_ak3_") as staging_str:
            staging_dir = pathlib.Path(staging_str)

            # Copy AK3 directory contents excluding .git
            for item in ak3_source.iterdir():
                if item.name == ".git":
                    continue
                dest = staging_dir / item.name
                if item.is_dir():
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)

            # Copy kernel image and dtbo artifacts
            for art in valid_artifacts:
                dest = staging_dir / art.name
                shutil.copy2(art, dest)
                logger.info(
                    "{}", f"Added artifact: {art.name} ({art.stat().st_size} bytes)"
                )

            # Create flashable zip using Python zipfile
            with zipfile.ZipFile(
                zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
            ) as zf:
                for root, _, files in os.walk(staging_dir):
                    for file in files:
                        full_path = pathlib.Path(root) / file
                        arcname = full_path.relative_to(staging_dir)
                        zf.write(full_path, arcname=str(arcname))

        # Compute SHA256 checksum
        hasher = hashlib.sha256()
        with open(zip_path, "rb") as f:
            while chunk := f.read(128 * 1024):
                hasher.update(chunk)
        sha256_hex = hasher.hexdigest()

        zip_size_mb = zip_path.stat().st_size / (1024 * 1024)
        logger.success("{}", f"Successfully packaged {zip_path} ({zip_size_mb:.2f} MB)")
        logger.info("{}", f"SHA256: {sha256_hex}")

        return zip_path, sha256_hex
