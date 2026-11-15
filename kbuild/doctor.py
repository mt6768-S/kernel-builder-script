"""
Environment diagnostic and health-check tools for kbuild (kb doctor).
Uses rich for beautiful reporting.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys

from rich.table import Table

from kbuild import __version__, console
from kbuild.paths import (
    KBUILD_AK3_DIR,
    KBUILD_CLANG_DIR,
    KBUILD_CONFIG_FILE,
    KBUILD_ROOT,
    get_symlink_path,
)

REQUIRED_SYSTEM_TOOLS = [
    "git",
    "make",
    "tar",
    "curl",
    "bc",
    "bison",
    "flex",
]

RECOMMENDED_TOOLS = [
    "zstd",
    "lz4",
    "zip",
]


def test_binary_execution(
    bin_path: pathlib.Path, version_flag: str = "--version"
) -> tuple[bool, str]:
    if not bin_path.is_file():
        return False, "Not found"
    if not os.access(bin_path, os.X_OK):
        return False, "Not executable"
    try:
        res = subprocess.run(
            [str(bin_path), version_flag],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode == 0 and res.stdout:
            first_line = res.stdout.splitlines()[0].strip()
            return True, first_line
        elif res.returncode in (-4, 132):
            return False, "CPU incompatible (SIGILL / missing AVX support)"
        return False, f"Exit code {res.returncode}"
    except Exception as e:
        return False, str(e)


def run_doctor() -> bool:
    """Runs full system diagnostics and prints structured report. Returns True if all healthy."""
    console.print()
    console.rule(f"[bold cyan]kbuild Doctor (v{__version__})[/bold cyan]", style="cyan")
    console.print()

    all_ok = True
    table = Table(title="System Diagnostic Results", header_style="bold cyan")
    table.add_column("Component", style="bold")
    table.add_column("Status")
    table.add_column("Details", style="dim")

    # 1. Python version
    py_ver = sys.version.split()[0]
    py_ok = sys.version_info >= (3, 12)
    if not py_ok:
        all_ok = False
    table.add_row(
        "Python Runtime",
        "[bold green]✓ OK[/bold green]" if py_ok else "[bold red]✗ FAIL[/bold red]",
        f"{py_ver} ({sys.executable})",
    )

    # 2. Required tools
    for tool in REQUIRED_SYSTEM_TOOLS:
        path = shutil.which(tool)
        if path:
            table.add_row(f"Tool: {tool}", "[bold green]✓ OK[/bold green]", path)
        else:
            all_ok = False
            table.add_row(
                f"Tool: {tool}",
                "[bold red]✗ MISSING[/bold red]",
                "Required for building/packaging",
            )

    # Recommended tools
    for tool in RECOMMENDED_TOOLS:
        path = shutil.which(tool)
        if path:
            table.add_row(f"Tool: {tool}", "[bold green]✓ OK[/bold green]", path)
        else:
            table.add_row(
                f"Tool: {tool}",
                "[bold yellow]! OPTIONAL[/bold yellow]",
                "Recommended for decompression",
            )

    # 3. ~/.kbuild directory & permissions
    root_exists = KBUILD_ROOT.is_dir()
    table.add_row(
        "kbuild Root",
        "[bold green]✓ OK[/bold green]"
        if root_exists
        else "[bold yellow]! CREATED ON RUN[/bold yellow]",
        str(KBUILD_ROOT),
    )

    # Config file & permissions
    if KBUILD_CONFIG_FILE.is_file():
        mode = oct(KBUILD_CONFIG_FILE.stat().st_mode & 0o777)
        is_secure = (KBUILD_CONFIG_FILE.stat().st_mode & 0o077) == 0
        cfg_status = (
            "[bold green]✓ OK[/bold green]"
            if is_secure
            else "[bold yellow]! INSECURE[/bold yellow]"
        )
        table.add_row(
            "Config File", cfg_status, f"{KBUILD_CONFIG_FILE} (permissions: {mode})"
        )
    else:
        table.add_row(
            "Config File",
            "[bold yellow]! DEFAULT[/bold yellow]",
            "Will use built-in defaults",
        )

    # 4. Toolchain check (Neutron Clang & System Clang)
    neutron_bin = KBUILD_CLANG_DIR / "bin" / "clang"
    if neutron_bin.is_file():
        is_ok, ver = test_binary_execution(neutron_bin)
        status = (
            "[bold green]✓ OK[/bold green]"
            if is_ok
            else "[bold red]✗ INCOMPATIBLE[/bold red]"
        )
        if not is_ok:
            all_ok = False
        table.add_row("Neutron Clang", status, f"{ver} ({neutron_bin})")
    else:
        table.add_row(
            "Neutron Clang",
            "[bold yellow]! NOT INSTALLED[/bold yellow]",
            "Will download lazily on first build or via 'kb setup'",
        )

    sys_clang = shutil.which("clang")
    if sys_clang:
        is_ok, ver = test_binary_execution(pathlib.Path(sys_clang))
        status = (
            "[bold green]✓ OK[/bold green]"
            if is_ok
            else "[bold red]✗ FAILED[/bold red]"
        )
        table.add_row("System Clang", status, f"{ver} ({sys_clang})")
    else:
        table.add_row(
            "System Clang", "[dim]- NOT FOUND[/dim]", "Fallback compiler not available"
        )

    # 5. AnyKernel3 cache
    ak3_script = KBUILD_AK3_DIR / "anykernel.sh"
    if ak3_script.is_file():
        table.add_row(
            "AnyKernel3 Cache", "[bold green]✓ CACHED[/bold green]", str(KBUILD_AK3_DIR)
        )
    else:
        table.add_row(
            "AnyKernel3 Cache",
            "[bold yellow]! NOT CACHED[/bold yellow]",
            "Will clone on first build or via 'kb setup'",
        )

    # 6. Global command symlink
    symlink = get_symlink_path()
    if symlink.is_symlink() or symlink.is_file():
        table.add_row("Command 'kb'", "[bold green]✓ LINKED[/bold green]", str(symlink))
    else:
        table.add_row(
            "Command 'kb'",
            "[bold yellow]! NOT LINKED[/bold yellow]",
            f"Link to {symlink}",
        )

    console.print(table)
    console.print()

    if all_ok:
        console.print(
            "[bold green]Doctor check passed: Environment is ready for building kernels.[/bold green]\n"
        )
    else:
        console.print(
            "[bold yellow]Doctor check found warnings/issues. Review the table above.[/bold yellow]\n"
        )

    return all_ok
