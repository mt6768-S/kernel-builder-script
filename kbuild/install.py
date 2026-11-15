"""
Pure Python installer for kbuild.
Sets up ~/.kbuild, virtual environment, editable install, symlinks, and shell rc hooks.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys

from loguru import logger

from kbuild import __version__, console
from kbuild.config import KbuildConfig, save_config
from kbuild.paths import (
    KBUILD_APP_DIR,
    KBUILD_BIN_DIR,
    KBUILD_CONFIG_FILE,
    KBUILD_VENV_DIR,
    ensure_kbuild_dirs,
)

RC_MARKER_START = "# >>> kbuild initialize >>>"
RC_MARKER_END = "# <<< kbuild initialize <<<"

SHELL_RC_BLOCK = f"""{RC_MARKER_START}
# !! Contents within this block are managed by 'kb' !!
export PATH="$HOME/.local/bin:$HOME/.kbuild/bin:$PATH"
[ -f "$HOME/.kbuild/bin/env.sh" ] && source "$HOME/.kbuild/bin/env.sh"
{RC_MARKER_END}
"""


def setup_filesystem_and_app() -> None:
    ensure_kbuild_dirs()
    current_repo = pathlib.Path(__file__).parent.parent.resolve()

    if current_repo != KBUILD_APP_DIR.resolve():
        logger.info("{}", f"Setting up kbuild app repository at {KBUILD_APP_DIR}...")
        if not KBUILD_APP_DIR.exists():
            if (current_repo / "pyproject.toml").is_file():
                shutil.copytree(
                    current_repo,
                    KBUILD_APP_DIR,
                    ignore=shutil.ignore_patterns(
                        ".git",
                        "__pycache__",
                        ".pytest_cache",
                        ".mypy_cache",
                        ".ruff_cache",
                        "venv",
                        ".venv",
                    ),
                )
                if (current_repo / ".git").is_dir():
                    shutil.copytree(current_repo / ".git", KBUILD_APP_DIR / ".git")
            else:
                subprocess.run(
                    [
                        "git",
                        "clone",
                        "https://github.com/mt6768-S/kernel-builder-script.git",
                        str(KBUILD_APP_DIR),
                    ],
                    check=True,
                )
        else:
            logger.info("{}", f"App directory {KBUILD_APP_DIR} already exists.")


def setup_virtualenv() -> None:
    logger.log("STEP", "{}", "[VENV] Preparing Python virtual environment...")
    pip_bin = KBUILD_VENV_DIR / "bin" / "pip"

    if not pip_bin.is_file():
        logger.info("{}", f"Creating virtualenv at {KBUILD_VENV_DIR}...")
        subprocess.run([sys.executable, "-m", "venv", str(KBUILD_VENV_DIR)], check=True)

    app_dir = (
        KBUILD_APP_DIR
        if KBUILD_APP_DIR.is_dir()
        else pathlib.Path(__file__).parent.parent.resolve()
    )

    logger.info("{}", f"Installing kbuild package in editable mode from {app_dir}...")
    subprocess.run([str(pip_bin), "install", "--upgrade", "pip"], check=True)
    subprocess.run([str(pip_bin), "install", "-e", str(app_dir)], check=True)
    logger.success("{}", "Virtualenv configured successfully.")


def create_bin_wrappers_and_symlinks() -> None:
    logger.log("STEP", "{}", "[BIN] Setting up CLI executable and symlinks...")
    kb_wrapper = KBUILD_BIN_DIR / "kb"

    wrapper_content = f"""#!/usr/bin/env bash
exec "{KBUILD_VENV_DIR}/bin/kb" "$@"
"""
    with open(kb_wrapper, "w", encoding="utf-8") as f:
        f.write(wrapper_content)
    kb_wrapper.chmod(0o755)
    logger.success("{}", f"Created executable wrapper at {kb_wrapper}")

    # Symlink ~/.local/bin/kb
    local_bin = pathlib.Path.home() / ".local" / "bin"
    local_bin.mkdir(parents=True, exist_ok=True)
    symlink_path = local_bin / "kb"

    if symlink_path.is_symlink() or symlink_path.is_file():
        symlink_path.unlink()

    symlink_path.symlink_to(kb_wrapper)
    logger.success("{}", f"Created symlink: {symlink_path} -> {kb_wrapper}")


def configure_shell_rc() -> None:
    logger.log(
        "STEP", "{}", "[SHELL] Configuring shell startup scripts (.bashrc, .zshrc)..."
    )
    home = pathlib.Path.home()
    rc_targets = [home / ".bashrc", home / ".zshrc"]

    for rc_file in rc_targets:
        if not rc_file.is_file():
            continue

        try:
            content = rc_file.read_text(encoding="utf-8")
        except Exception:
            continue

        # Check if already present
        if RC_MARKER_START in content:
            # Replace existing block idempotently
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
            clean_content = "".join(new_lines).rstrip() + "\n\n" + SHELL_RC_BLOCK + "\n"
            rc_file.write_text(clean_content, encoding="utf-8")
            logger.success("{}", f"Updated kbuild environment block in {rc_file}")
        else:
            updated = content.rstrip() + "\n\n" + SHELL_RC_BLOCK + "\n"
            rc_file.write_text(updated, encoding="utf-8")
            logger.success("{}", f"Appended kbuild environment block to {rc_file}")


def run_install() -> int:
    console.print()
    console.rule(
        f"[bold cyan]Installing kbuild (v{__version__})[/bold cyan]", style="cyan"
    )
    console.print()

    try:
        setup_filesystem_and_app()
        setup_virtualenv()
        create_bin_wrappers_and_symlinks()
        configure_shell_rc()

        # Initialize config if not existing
        if not KBUILD_CONFIG_FILE.is_file():
            save_config(KbuildConfig())
            logger.success(
                "{}", f"Initialized default configuration at {KBUILD_CONFIG_FILE}"
            )

        console.print()
        console.rule("[bold green]Installation Complete[/bold green]", style="green")
        console.print("[bold]You can now run 'kb' from anywhere![/bold]\n")

        # Run doctor using installed kb executable
        kb_bin = KBUILD_BIN_DIR / "kb"
        if kb_bin.is_file():
            subprocess.run([str(kb_bin), "doctor"], check=False)
        return 0
    except Exception as e:
        logger.error("{}", f"Installation failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(run_install())
