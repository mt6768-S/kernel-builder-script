"""
Environment and toolchain information display for kbuild (kb info).
"""

from __future__ import annotations

import json
import pathlib
import shutil

from rich.table import Table

from kbuild import __version__, console
from kbuild.doctor import test_binary_execution
from kbuild.paths import (
    KBUILD_AK3_DIR,
    KBUILD_CLANG_DIR,
    KBUILD_ROOT,
    KBUILD_TOOLCHAIN_INFO_FILE,
    get_symlink_path,
)
from kbuild.settings import load_config


def show_info() -> None:
    cfg = load_config()

    console.print()
    console.rule(
        f"[bold cyan]kbuild Environment & Toolchain Info (v{__version__})[/bold cyan]",
        style="cyan",
    )
    console.print(f"[bold]Root Directory:[/bold] {KBUILD_ROOT}\n")

    # Toolchain info
    toolchain_meta = {}
    if KBUILD_TOOLCHAIN_INFO_FILE.is_file():
        try:
            with open(KBUILD_TOOLCHAIN_INFO_FILE, encoding="utf-8") as f:
                toolchain_meta = json.load(f)
        except Exception:
            pass

    table = Table(title="Toolchain & Integration Status", header_style="bold cyan")
    table.add_column("Component", style="bold")
    table.add_column("Status")
    table.add_column("Details", style="dim")

    # Neutron Clang
    neutron_bin = KBUILD_CLANG_DIR / "bin" / "clang"
    if neutron_bin.is_file():
        is_ok, ver = test_binary_execution(neutron_bin)
        tag = toolchain_meta.get("tag", "custom")
        status = (
            "[bold green]Installed[/bold green]"
            if is_ok
            else "[bold red]Incompatible[/bold red]"
        )
        table.add_row("Neutron Clang", status, f"Tag: {tag} | {ver}")
    else:
        table.add_row(
            "Neutron Clang",
            "[bold yellow]Not installed[/bold yellow]",
            str(KBUILD_CLANG_DIR),
        )

    # System Clang
    sys_clang = shutil.which("clang")
    if sys_clang:
        is_ok, ver = test_binary_execution(pathlib.Path(sys_clang))
        status = (
            "[bold green]Available[/bold green]"
            if is_ok
            else "[bold red]Failed[/bold red]"
        )
        table.add_row("System Clang", status, f"{ver} ({sys_clang})")
    else:
        table.add_row("System Clang", "[dim]Not found[/dim]", "-")

    # AnyKernel3
    ak3_script = KBUILD_AK3_DIR / "anykernel.sh"
    if ak3_script.is_file():
        table.add_row(
            "AnyKernel3 Cache", "[bold green]Cached[/bold green]", str(KBUILD_AK3_DIR)
        )
    else:
        table.add_row(
            "AnyKernel3 Cache",
            "[bold yellow]Not cached[/bold yellow]",
            str(KBUILD_AK3_DIR),
        )

    # Symlink
    symlink = get_symlink_path()
    if symlink.is_symlink() or symlink.is_file():
        table.add_row("Global CLI", "[bold green]Linked[/bold green]", str(symlink))
    else:
        table.add_row(
            "Global CLI",
            "[bold yellow]Not linked[/bold yellow]",
            f"Expected at {symlink}",
        )

    console.print(table)
    console.print()

    # Active configuration summary
    cfg_table = Table(title="Active Build Settings", header_style="bold cyan")
    cfg_table.add_column("Feature", style="bold")
    cfg_table.add_column("Setting")

    def format_bool(val: bool) -> str:
        return (
            "[bold green]Enabled (true)[/bold green]"
            if val
            else "[bold red]Disabled (false)[/bold red]"
        )

    cfg_table.add_row("Telegram Upload", format_bool(cfg.telegram))
    cfg_table.add_row("GoFile Upload", format_bool(cfg.gofile))
    cfg_table.add_row("DTBO Generation", format_bool(cfg.dtbo))
    cfg_table.add_row("Clean Build", format_bool(cfg.clean))
    cfg_table.add_row(
        "KernelSU (KSU)",
        f"{format_bool(cfg.ksu)} (Target: {cfg.ksu_target})\n[dim]Script: {cfg.ksu_setup}[/dim]",
    )
    cfg_table.add_row(
        "NoMount",
        f"{format_bool(cfg.nomount)} (Target: {cfg.nomount_target})\n[dim]Script: {cfg.nomount_setup}[/dim]",
    )
    cfg_table.add_row("Zip Prefix", f"[bold]{cfg.zip_prefix}[/bold]")
    cfg_table.add_row("Default Defconfig", f"[bold]{cfg.default_defconfig}[/bold]")
    host_str = cfg.host or "auto"
    user_str = cfg.user or "auto"
    cfg_table.add_row("Build Host / User", f"{user_str}@{host_str}")

    console.print(cfg_table)
    console.print()
