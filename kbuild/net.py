"""
Network and download utilities using the 'requests' and 'rich' modules.
"""

from __future__ import annotations

import os
import pathlib
from typing import Any

import requests
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from kbuild import __version__
from kbuild.console import console

DEFAULT_USER_AGENT = f"kbuild/{__version__} (Linux x86_64)"


def http_get_json(
    url: str, headers: dict[str, str] | None = None, timeout: int = 15
) -> Any:
    """Performs HTTP GET using requests and returns parsed JSON."""
    req_headers = {"User-Agent": DEFAULT_USER_AGENT}
    if headers:
        req_headers.update(headers)
    resp = requests.get(url, headers=req_headers, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def download_file(
    url: str,
    dest_path: pathlib.Path,
    description: str = "Downloading",
    timeout: int = 60,
) -> pathlib.Path:
    """
    Downloads a file using requests and rich streaming progress.
    Writes to a temporary file first and atomically moves to dest_path.
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = dest_path.with_suffix(f"{dest_path.suffix}.tmp.{os.getpid()}")

    headers = {"User-Agent": DEFAULT_USER_AGENT}

    try:
        with requests.get(url, headers=headers, stream=True, timeout=timeout) as resp:
            resp.raise_for_status()
            total_size = int(resp.headers.get("content-length", 0))

            with Progress(
                TextColumn("[bold cyan]{task.description}"),
                BarColumn(),
                DownloadColumn(),
                TransferSpeedColumn(),
                TimeRemainingColumn(),
                console=console,
            ) as progress:
                task_id = progress.add_task(
                    description, total=total_size if total_size > 0 else None
                )

                with open(temp_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=128 * 1024):
                        if chunk:
                            f.write(chunk)
                            progress.update(task_id, advance=len(chunk))

        temp_path.replace(dest_path)
        return dest_path
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise
