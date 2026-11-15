"""
Rich console logging and formatting for kbuild with bootstrap fallback.
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


def log_info(msg: str) -> None:
    if _rich:
        console.print(f"[bold cyan][*][/bold cyan] {msg}")
    else:
        print(f"[*] {msg}", flush=True)


def log_step(step: str, title: str) -> None:
    if _rich:
        console.print()
        console.rule(f"[bold blue][{step}] {title}[/bold blue]", style="blue")
    else:
        print(f"\n=== [{step}] {title} ===", flush=True)


def log_success(msg: str) -> None:
    if _rich:
        console.print(f"[bold green][✓][/bold green] {msg}")
    else:
        print(f"[✓] {msg}", flush=True)


def log_warn(msg: str) -> None:
    if _rich:
        console.print(f"[bold yellow][!][/bold yellow] {msg}")
    else:
        print(f"[!] {msg}", flush=True)


def log_error(msg: str) -> None:
    if _rich:
        err_console.print(f"[bold red][✗][/bold red] {msg}")
    else:
        print(f"[✗] {msg}", file=sys.stderr, flush=True)


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
