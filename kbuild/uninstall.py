"""
Pure Python uninstaller for kbuild.
Removes ~/.kbuild, symlinks, and shell rc hooks.
"""

from __future__ import annotations

import pathlib
import shutil
import sys

from kbuild import __version__
from kbuild.console import console, log_error, log_step, log_success, log_warn
from kbuild.install import RC_MARKER_END, RC_MARKER_START
from kbuild.paths import KBUILD_ROOT, get_symlink_path


def clean_shell_rc() -> None:
    home = pathlib.Path.home()
    rc_targets = [home / ".bashrc", home / ".zshrc"]

    for rc_file in rc_targets:
        if not rc_file.is_file():
            continue

        try:
            content = rc_file.read_text(encoding="utf-8")
        except Exception:
            continue

        if RC_MARKER_START in content:
            lines = content.splitlines(keepends=True)
            new_lines = []
            skipping = False
            for line in lines:
                if RC_MARKER_START in line:
                    skipping = True
                    continue
                if RC_MARKER_END in line:
                    skipping = False
                    continue
                if not skipping:
                    new_lines.append(line)
            clean_content = "".join(new_lines).rstrip() + "\n"
            rc_file.write_text(clean_content, encoding="utf-8")
            log_success(f"Removed kbuild environment block from {rc_file}")


def run_uninstall(assume_yes: bool = False) -> int:
    console.print()
    console.rule(
        f"[bold red]Uninstalling kbuild (v{__version__})[/bold red]", style="red"
    )
    console.print()

    if not assume_yes and sys.stdin.isatty():
        res = (
            input(
                f"Are you sure you want to completely remove {KBUILD_ROOT} and kbuild symlinks? [y/N]: "
            )
            .strip()
            .lower()
        )
        if res not in ("y", "yes"):
            console.print("[yellow]Uninstallation cancelled.[/yellow]")
            return 0

    log_step("UNINSTALL", "Removing symlinks and shell integration...")
    symlink = get_symlink_path()
    if symlink.is_symlink() or symlink.is_file():
        try:
            symlink.unlink()
            log_success(f"Removed symlink: {symlink}")
        except Exception as e:
            log_warn(f"Failed to remove symlink {symlink}: {e}")

    # Remove any old pb symlink if present
    old_pb = pathlib.Path.home() / ".local" / "bin" / "pb"
    if old_pb.is_symlink() or old_pb.is_file():
        try:
            old_pb.unlink()
            log_success(f"Removed legacy pb symlink: {old_pb}")
        except Exception:
            pass

    clean_shell_rc()

    if KBUILD_ROOT.exists():
        log_step("ROOT", f"Deleting {KBUILD_ROOT}...")
        try:
            shutil.rmtree(KBUILD_ROOT, ignore_errors=True)
            log_success(f"Deleted {KBUILD_ROOT}")
        except Exception as e:
            log_error(f"Failed to delete {KBUILD_ROOT}: {e}")
            return 1

    console.print()
    console.rule(
        "[bold green]kbuild Uninstalled Successfully[/bold green]", style="green"
    )
    return 0


if __name__ == "__main__":
    yes_flag = "--yes" in sys.argv or "-y" in sys.argv
    sys.exit(run_uninstall(assume_yes=yes_flag))
