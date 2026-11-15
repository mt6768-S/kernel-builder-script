"""
GoFile API helper using the requests module for kbuild.
"""

from __future__ import annotations

import pathlib
from collections.abc import Sequence

import requests
from loguru import logger


class GoFileUploader:
    @staticmethod
    def get_upload_server() -> str | None:
        try:
            resp = requests.get(
                "https://api.gofile.io/servers",
                headers={"User-Agent": "kbuild"},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                servers = data.get("data", {}).get("servers", [])
                if servers:
                    return servers[0].get("name")
        except Exception as e:
            logger.warning("{}", f"Failed to fetch GoFile servers list: {e}")
        return None

    @classmethod
    def upload_file(cls, file_path: pathlib.Path) -> str | None:
        pages = cls.upload_files([file_path])
        return pages[0] if pages else None

    @classmethod
    def upload_files(cls, file_paths: Sequence[pathlib.Path]) -> list[str]:
        valid_files = [p for p in file_paths if p and p.is_file()]
        if not valid_files:
            return []

        server = cls.get_upload_server()
        if not server:
            logger.error("{}", "Could not determine GoFile upload server.")
            return []

        upload_url = f"https://{server}.gofile.io/uploadFile"
        parent_folder_id = None
        download_pages = []

        for fpath in valid_files:
            logger.info("{}", f"Uploading {fpath.name} to GoFile ({server})...")
            try:
                data = {}
                if parent_folder_id:
                    data["folderId"] = parent_folder_id

                with open(fpath, "rb") as f:
                    files = {"file": (fpath.name, f)}
                    resp = requests.post(
                        upload_url, data=data, files=files, timeout=300
                    )

                if resp.status_code == 200:
                    res_json = resp.json()
                    res_data = res_json.get("data", {})
                    d_page = res_data.get("downloadPage")
                    parent_folder_id = res_data.get("parentFolder") or parent_folder_id
                    if d_page:
                        download_pages.append(d_page)
                        logger.success("{}", f"GoFile download link: {d_page}")
                else:
                    logger.error(
                        "{}", f"GoFile upload failed: {resp.status_code} {resp.text}"
                    )
            except Exception as e:
                logger.error("{}", f"GoFile upload exception for {fpath.name}: {e}")

        return download_pages
