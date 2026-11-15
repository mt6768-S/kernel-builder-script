"""
Fast, modular Android kernel build and packaging toolchain.
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from rich.console import Console

__version__ = "1.0.0"
__author__ = "mt6768-S"

console = Console(highlight=False)
err_console = Console(stderr=True, highlight=False)

_LEVEL_STYLES = {
    "INFO": ("[*]", "bold cyan"),
    "SUCCESS": ("[✓]", "bold green"),
    "WARNING": ("[!]", "bold yellow"),
    "ERROR": ("[✗]", "bold red"),
}


def _sink(message: Any) -> None:
    record = message.record
    level = record["level"].name
    if level == "STEP":
        console.print()
        console.rule(f"[bold blue]{record['message']}[/bold blue]", style="blue")
        return
    glyph, style = _LEVEL_STYLES.get(level, _LEVEL_STYLES["INFO"])
    target = err_console if level == "ERROR" else console
    target.print(f"[{style}]{glyph}[/{style}] {record['message']}")


try:
    logger.level("STEP")
except ValueError:
    logger.level("STEP", no=25)

logger.remove()
logger.add(_sink, level="INFO")
