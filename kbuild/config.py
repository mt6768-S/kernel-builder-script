"""
Configuration manager and schema for kbuild.
Loads, validates, and persists user settings in ~/.kbuild/config.json with 0600 permissions.
"""

from __future__ import annotations

import dataclasses
import json
import os
import pathlib
from typing import Any

from loguru import logger

from kbuild import console
from kbuild.errors import ConfigError
from kbuild.paths import (
    KBUILD_CONFIG_FILE,
    ensure_kbuild_dirs,
    find_local_config,
)


@dataclasses.dataclass
class KbuildConfig:
    telegram: bool = True
    gofile: bool = False
    clean: bool = True
    ksu: bool = False
    nomount: bool = False
    jobs: int | None = None
    cc: str | None = None
    zip_prefix: str = "Skyron"
    host: str | None = None
    user: str | None = None
    bot_token: str | None = None
    chat_id: str | None = None
    ak3_repo: str = "https://github.com/mt6768-S/AnyKernel3"
    ksu_target: str = "master"
    ksu_setup: str = (
        "https://raw.githubusercontent.com/backslashxx/KernelSU/master/kernel/setup.sh"
    )
    nomount_target: str = "dev"
    nomount_setup: str = "https://raw.githubusercontent.com/maxsteeel/nomount/refs/heads/dev/kernel/setup.sh"
    default_defconfig: str = "vendor/mt6768_defconfig"

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KbuildConfig:
        known_fields = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


def parse_bool(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    v = str(val).lower().strip()
    if v in ("true", "1", "yes", "on", "y", "t", "enable", "enabled"):
        return True
    if v in ("false", "0", "no", "off", "n", "f", "disable", "disabled"):
        return False
    raise ConfigError(f"Invalid boolean value: {val}")


def load_config(cwd: pathlib.Path | None = None) -> KbuildConfig:
    """
    Loads configuration merged from:
    1. Built-in defaults
    2. Global ~/.kbuild/config.json
    3. Local .kb.json / kb.json / .pb.json / pb.json in cwd
    """
    cfg_data = KbuildConfig().to_dict()

    if KBUILD_CONFIG_FILE.is_file():
        try:
            with open(KBUILD_CONFIG_FILE, encoding="utf-8") as f:
                saved = json.load(f)
                if isinstance(saved, dict):
                    for deprecated in (
                        "upload",
                        "source",
                        "device",
                        "defconfig",
                        "device_config",
                    ):
                        saved.pop(deprecated, None)
                    cfg_data.update(saved)
        except Exception as e:
            logger.warning("{}", f"Failed to read {KBUILD_CONFIG_FILE}: {e}")

    local_path = find_local_config(cwd)
    if local_path:
        try:
            with open(local_path, encoding="utf-8") as f:
                local_data = json.load(f)
                if isinstance(local_data, dict):
                    for deprecated in (
                        "upload",
                        "source",
                        "device",
                        "defconfig",
                        "device_config",
                    ):
                        local_data.pop(deprecated, None)
                    cfg_data.update(local_data)
        except Exception as e:
            logger.warning("{}", f"Failed to read local config {local_path}: {e}")

    return KbuildConfig.from_dict(cfg_data)


def save_config(cfg: KbuildConfig) -> None:
    """Saves configuration to ~/.kbuild/config.json with 0600 permissions."""
    ensure_kbuild_dirs()
    data = cfg.to_dict()

    temp_path = KBUILD_CONFIG_FILE.with_suffix(f".tmp.{os.getpid()}")
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        mode = 0o600
        fd = os.open(str(temp_path), flags, mode)
        with open(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        temp_path.replace(KBUILD_CONFIG_FILE)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def update_config_from_pairs(pairs: list[str]) -> KbuildConfig:
    """Updates configuration from a list of key=value pairs."""
    cfg = load_config()

    if not pairs:
        show_config(cfg)
        return cfg

    first = pairs[0].strip().lower()
    if first in ("reset", "default", "defaults"):
        cfg = KbuildConfig()
        save_config(cfg)
        logger.success("{}", "Configuration reset to default values.")
        show_config(cfg)
        return cfg

    updated_count = 0
    for item in pairs:
        if "=" not in item:
            logger.warning(
                "{}",
                f"Ignored invalid config pair '{item}'. Expected format: key=value",
            )
            continue

        key, val = item.split("=", 1)
        key = key.strip().lower()
        val = val.strip()

        try:
            if key in ("telegram", "tg"):
                cfg.telegram = parse_bool(val)
                updated_count += 1
            elif key in ("gofile", "gf"):
                cfg.gofile = parse_bool(val)
                updated_count += 1
            elif key in ("clean", "distclean", "mrproper"):
                cfg.clean = parse_bool(val)
                updated_count += 1
            elif key in ("ksu", "kernelsu", "xxksu"):
                cfg.ksu = parse_bool(val)
                updated_count += 1
            elif key in ("nomount",):
                cfg.nomount = parse_bool(val)
                updated_count += 1
            elif key in ("jobs", "threads", "cores"):
                if val.lower() in ("auto", "none", "null", "0", ""):
                    cfg.jobs = None
                elif val.isdigit():
                    cfg.jobs = int(val)
                else:
                    raise ConfigError(f"Invalid integer for jobs: {val}")
                updated_count += 1
            elif key == "ksu_target":
                cfg.ksu_target = val
                updated_count += 1
            elif key == "ksu_setup":
                cfg.ksu_setup = val
                updated_count += 1
            elif key == "nomount_target":
                cfg.nomount_target = val
                updated_count += 1
            elif key == "nomount_setup":
                cfg.nomount_setup = val
                updated_count += 1
            elif key == "zip_prefix":
                cfg.zip_prefix = val
                updated_count += 1
            elif key == "ak3_repo":
                cfg.ak3_repo = val
                updated_count += 1
            elif key == "default_defconfig":
                cfg.default_defconfig = val
                updated_count += 1
            elif key in ("cc", "host", "user", "bot_token", "chat_id"):
                setattr(
                    cfg, key, val if val.lower() not in ("none", "null", "") else None
                )
                updated_count += 1
            else:
                logger.warning("{}", f"Unknown config key '{key}'. Ignored.")
        except ConfigError as ce:
            logger.error("{}", str(ce))

    save_config(cfg)
    logger.success("{}", f"Updated {updated_count} setting(s) in {KBUILD_CONFIG_FILE}")
    show_config(cfg)
    return cfg


def show_config(cfg: KbuildConfig | None = None) -> None:
    if cfg is None:
        cfg = load_config()

    from rich.table import Table

    table = Table(
        title="kbuild Configuration (~/.kbuild/config.json)", header_style="bold cyan"
    )
    table.add_column("Setting", style="bold")
    table.add_column("Key", style="dim")
    table.add_column("Value")

    def format_bool(val: bool) -> str:
        return "[bold green]true[/bold green]" if val else "[bold red]false[/bold red]"

    def format_opt(val: Any) -> str:
        if val is None:
            return "[dim]auto / null[/dim]"
        return f"[bold]{val}[/bold]"

    bot_token_str = "[dim]***set***[/dim]" if cfg.bot_token else "[dim]null[/dim]"

    rows = [
        ("Telegram Upload", "telegram", format_bool(cfg.telegram)),
        ("GoFile Upload", "gofile", format_bool(cfg.gofile)),
        ("Clean Build", "clean", format_bool(cfg.clean)),
        ("KernelSU (KSU)", "ksu", format_bool(cfg.ksu)),
        ("KernelSU Target", "ksu_target", format_opt(cfg.ksu_target)),
        ("KernelSU Setup URL", "ksu_setup", format_opt(cfg.ksu_setup)),
        ("NoMount", "nomount", format_bool(cfg.nomount)),
        ("NoMount Target", "nomount_target", format_opt(cfg.nomount_target)),
        ("NoMount Setup URL", "nomount_setup", format_opt(cfg.nomount_setup)),
        ("Parallel Jobs", "jobs", format_opt(cfg.jobs)),
        ("Compiler (CC)", "cc", format_opt(cfg.cc)),
        ("Zip Prefix", "zip_prefix", format_opt(cfg.zip_prefix)),
        ("Default Defconfig", "default_defconfig", format_opt(cfg.default_defconfig)),
        ("Build Host", "host", format_opt(cfg.host)),
        ("Build User", "user", format_opt(cfg.user)),
        ("Telegram Bot Token", "bot_token", bot_token_str),
        ("Telegram Chat ID", "chat_id", format_opt(cfg.chat_id)),
        ("AnyKernel3 Repo", "ak3_repo", format_opt(cfg.ak3_repo)),
    ]

    for label, key, val in rows:
        table.add_row(label, key, val)

    console.print()
    console.print(table)
    console.print("[dim]Usage: kb config key=value ... | kb config reset[/dim]\n")
