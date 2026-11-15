"""
Rich console logging and formatting for kbuild with bootstrap fallback.

Log records are routed through `loguru` when it is installed; otherwise the
helpers below fall back to direct printing.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable, Sequence
from typing import Any

try:
    from rich.console import Console
    from rich.table import Table

    _rich = True
    console = Console(highlight=False)
    err_console = Console(stderr=True, highlight=False)
except ImportError:
    _rich = False

    class _DummyConsole:
        def print(self, *args: Any, **kwargs: Any) -> None:
            clean_args = []
            for a in args:
                s = str(a)
                # Strip simple rich tags if any
                for tag in (
                    "[bold cyan]",
                    "[/bold cyan]",
                    "[bold blue]",
                    "[/bold blue]",
                    "[bold green]",
                    "[/bold green]",
                    "[bold red]",
                    "[/bold red]",
                    "[bold yellow]",
                    "[/bold yellow]",
                    "[bold]",
                    "[/bold]",
                    "[dim]",
                    "[/dim]",
                    "[cyan]",
                    "[/cyan]",
                    "[yellow]",
                    "[/yellow]",
                ):
                    s = s.replace(tag, "")
                clean_args.append(s)
            print(*clean_args, flush=True)

        def rule(self, title: str = "", *args: Any, **kwargs: Any) -> None:
            t = (
                title.replace("[bold cyan]", "")
                .replace("[/bold cyan]", "")
                .replace("[bold blue]", "")
                .replace("[/bold blue]", "")
                .replace("[bold green]", "")
                .replace("[/bold green]", "")
                .replace("[bold red]", "")
                .replace("[/bold red]", "")
            )
            print(f"\n=== {t} ===", flush=True)

    console = _DummyConsole()  # type: ignore
    err_console = _DummyConsole()  # type: ignore

try:
    from loguru import logger

    _loguru = True
except ImportError:
    _loguru = False


_PREFIXES = {
    "INFO": "[bold cyan][*][/bold cyan]",
    "SUCCESS": "[bold green][✓][/bold green]",
    "WARNING": "[bold yellow][!][/bold yellow]",
    "ERROR": "[bold red][✗][/bold red]",
}
_PLAIN_PREFIXES = {
    "INFO": "[*]",
    "SUCCESS": "[✓]",
    "WARNING": "[!]",
    "ERROR": "[✗]",
}


def _render(level: str, msg: str) -> None:
    if _rich:
        target = err_console if level == "ERROR" else console
        target.print(f"{_PREFIXES.get(level, _PREFIXES['INFO'])} {msg}")
    else:
        prefix = _PLAIN_PREFIXES.get(level, _PLAIN_PREFIXES["INFO"])
        stream = sys.stderr if level == "ERROR" else sys.stdout
        print(f"{prefix} {msg}", file=stream, flush=True)


if _loguru:
    logger.remove()

    def _sink(message: Any) -> None:
        _render(message.record["level"].name, message.record["message"])

    logger.add(_sink, level="INFO")


def log_info(msg: str) -> None:
    if _loguru:
        logger.info("{}", msg)
    else:
        _render("INFO", msg)


def log_step(step: str, title: str) -> None:
    if _rich:
        console.print()
        console.rule(f"[bold blue][{step}] {title}[/bold blue]", style="blue")
    else:
        print(f"\n=== [{step}] {title} ===", flush=True)


def log_success(msg: str) -> None:
    if _loguru:
        logger.success("{}", msg)
    else:
        _render("SUCCESS", msg)


def log_warn(msg: str) -> None:
    if _loguru:
        logger.warning("{}", msg)
    else:
        _render("WARNING", msg)


def log_error(msg: str) -> None:
    if _loguru:
        logger.error("{}", msg)
    else:
        _render("ERROR", msg)


def print_table(
    title: str, headers: Sequence[str], rows: Iterable[Sequence[Any]]
) -> None:
    if _rich:
        table = Table(title=title, show_lines=False, header_style="bold cyan")
        for h in headers:
            table.add_column(h)
        for row in rows:
            table.add_row(*[str(c) for c in row])
        console.print(table)
    else:
        print(f"\n--- {title} ---")
        for row in rows:
            print(" | ".join(str(c) for c in row))
        print()
