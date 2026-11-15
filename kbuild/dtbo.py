"""
Device Tree Blob Overlay (DTBO) image generation wrapper for kbuild.
Finds compiled .dtbo files in out/arch/arm64/boot/dts and packages dtbo.img.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

from loguru import logger


def generate_dtbo_image(out_dir: pathlib.Path) -> pathlib.Path | None:
    """
    Searches out_dir/arch/arm64/boot/dts for *.dtbo files and creates dtbo.img.
    Returns path to created dtbo.img or None if no dtbo files found.
    """
    dts_dir = out_dir / "arch" / "arm64" / "boot" / "dts"
    if not dts_dir.is_dir():
        return None

    dtbo_files = sorted(list(dts_dir.glob("**/*.dtbo")))
    if not dtbo_files:
        return None

    logger.log(
        "STEP",
        "{}",
        f"[DTBO] Found {len(dtbo_files)} DTBO file(s), generating dtbo.img...",
    )
    output_dtbo = out_dir / "arch" / "arm64" / "boot" / "dtbo.img"

    vendor_tool = pathlib.Path(__file__).parent / "vendor" / "mkdtboimg.py"

    cmd = [
        sys.executable,
        str(vendor_tool),
        "create",
        str(output_dtbo),
        "--page_size=2048",
    ] + [str(p) for p in dtbo_files]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0 and output_dtbo.is_file():
        logger.success(
            "{}",
            f"Generated DTBO image at {output_dtbo} ({output_dtbo.stat().st_size} bytes)",
        )
        return output_dtbo
    else:
        err = res.stderr.strip() or res.stdout.strip()
        logger.warning("{}", f"Failed to generate dtbo.img: {err}")
        return None
