"""
Configuration schema and persistence for kbuild, backed by configmanager.

Settings are stored in ~/.kbuild/config.json and can be overridden by a local
project file (.kb.json, kb.json, .pb.json, or pb.json).
"""

from __future__ import annotations

import os
from typing import Any

from configmanager import Item, PlainConfig
from loguru import logger

from kbuild import console, paths

SCHEMA = [
    ("telegram", Item(type=bool, default=True)),
    ("gofile", Item(type=bool, default=False)),
    ("dtbo", Item(type=bool, default=True)),
    ("clean", Item(type=bool, default=True)),
    ("ksu", Item(type=bool, default=False)),
    ("nomount", Item(type=bool, default=False)),
    ("jobs", Item(type=int, default=None)),
    ("cc", Item(type=str, default=None)),
    ("zip_prefix", Item(type=str, default="Skyron")),
    ("host", Item(type=str, default=None)),
    ("user", Item(type=str, default=None)),
    ("bot_token", Item(type=str, default=None)),
    ("chat_id", Item(type=str, default=None)),
    ("ak3_repo", Item(type=str, default="https://github.com/mt6768-S/AnyKernel3")),
    ("ksu_target", Item(type=str, default="master")),
    (
        "ksu_setup",
        Item(
            type=str,
            default="https://raw.githubusercontent.com/backslashxx/KernelSU/master/kernel/setup.sh",
        ),
    ),
    ("nomount_target", Item(type=str, default="dev")),
    (
        "nomount_setup",
        Item(
            type=str,
            default="https://raw.githubusercontent.com/maxsteeel/nomount/refs/heads/dev/kernel/setup.sh",
        ),
    ),
    ("default_defconfig", Item(type=str, default="vendor/mt6768_defconfig")),
]

SETTING_KEYS = {name for name, _ in SCHEMA}

BOOL_KEYS = {"telegram", "gofile", "dtbo", "clean", "ksu", "nomount"}

KEY_ALIASES = {
    "tg": "telegram",
    "gf": "gofile",
    "distclean": "clean",
    "mrproper": "clean",
    "kernelsu": "ksu",
    "xxksu": "ksu",
    "threads": "jobs",
    "cores": "jobs",
}

_TRUTHY = {"true", "1", "yes", "on", "y", "t", "enable", "enabled"}
_FALSEY = {"false", "0", "no", "off", "n", "f", "disable", "disabled"}
_NULL_VALUES = {"none", "null", ""}


class KbuildConfig(PlainConfig):
    def __init__(self) -> None:
        super().__init__(SCHEMA)


def load_config(cwd=None) -> KbuildConfig:
    cfg = KbuildConfig()
    sources = []

    if paths.KBUILD_CONFIG_FILE.is_file():
        sources.append(paths.KBUILD_CONFIG_FILE)

    local_path = paths.find_local_config(cwd)
    if local_path:
        sources.append(local_path)

    for source in sources:
        try:
            cfg.json.load(str(source))
        except Exception as e:
            logger.warning("{}", f"Failed to read {source}: {e}")

    env_chat = (
        os.environ.get("TELEGRAM_CHAT_ID")
        or os.environ.get("TG_CHAT_ID")
        or os.environ.get("CHAT_ID")
        or os.environ.get("TG_CHAT")
    )
    if env_chat and env_chat.strip():
        cfg.chat_id = env_chat.strip()

    env_token = (
        os.environ.get("TELEGRAM_BOT_TOKEN")
        or os.environ.get("TG_BOT_TOKEN")
        or os.environ.get("BOT_TOKEN")
        or os.environ.get("TG_TOKEN")
    )
    if env_token and env_token.strip():
        cfg.bot_token = env_token.strip()

    return cfg


def save_config(cfg: KbuildConfig) -> None:
    """Saves configuration to ~/.kbuild/config.json with 0600 permissions."""
    paths.ensure_kbuild_dirs()
    text = cfg.json.dumps(with_defaults=True) + "\n"

    temp_path = paths.KBUILD_CONFIG_FILE.with_suffix(f".tmp.{os.getpid()}")
    try:
        fd = os.open(str(temp_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with open(fd, "w", encoding="utf-8") as f:
            f.write(text)
        temp_path.replace(paths.KBUILD_CONFIG_FILE)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _set_value(cfg: KbuildConfig, key: str, val: str) -> None:
    if key in BOOL_KEYS:
        lowered = val.lower()
        if lowered not in _TRUTHY and lowered not in _FALSEY:
            raise ValueError(f"Invalid boolean value for {key}: {val}")
        cfg[key] = lowered in _TRUTHY
    elif key == "jobs":
        if val.lower() in ("auto", "none", "null", "0", ""):
            cfg["jobs"] = None
        elif val.isdigit():
            cfg["jobs"] = int(val)
        else:
            raise ValueError(f"Invalid integer for jobs: {val}")
    else:
        cfg[key] = None if val.lower() in _NULL_VALUES else val


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
        key = KEY_ALIASES.get(key, key)

        if key not in SETTING_KEYS:
            logger.warning("{}", f"Unknown config key '{key}'. Ignored.")
            continue

        try:
            _set_value(cfg, key, val)
            updated_count += 1
        except ValueError as e:
            logger.error("{}", str(e))

    save_config(cfg)
    logger.success(
        "{}", f"Updated {updated_count} setting(s) in {paths.KBUILD_CONFIG_FILE}"
    )
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

    def format_bool(val: Any) -> str:
        return "[bold green]true[/bold green]" if val else "[bold red]false[/bold red]"

    def format_opt(val: Any) -> str:
        if val is None:
            return "[dim]auto / null[/dim]"
        return f"[bold]{val}[/bold]"

    bot_token_str = "[dim]***set***[/dim]" if cfg.bot_token else "[dim]null[/dim]"

    rows = [
        ("Telegram Upload", "telegram", format_bool(cfg.telegram)),
        ("GoFile Upload", "gofile", format_bool(cfg.gofile)),
        ("DTBO Generation", "dtbo", format_bool(cfg.dtbo)),
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
