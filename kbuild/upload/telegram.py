"""
Telegram API helper using the requests module for kbuild.
Sends status messages, logs, and artifacts conforming to docs/ExampleTexts.md.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Sequence

import requests

from kbuild.console import log_error, log_info, log_success, log_warn

MAX_MEDIA_GROUP_BYTES = 48 * 1024 * 1024  # 48 MB


class TelegramUploader:
    def __init__(self, bot_token: str | None, chat_id: str | None):
        self.bot_token = (bot_token or "").strip()
        self.chat_id = (chat_id or "").strip()
        self.base_url = (
            f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else ""
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def send_message(self, text: str) -> bool:
        if not self.is_configured:
            log_warn("Telegram bot token or chat ID missing; skipping message.")
            return False

        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            resp = requests.post(url, data=payload, timeout=20)
            if resp.status_code == 200 and resp.json().get("ok"):
                return True
            log_warn(f"Telegram sendMessage failed: {resp.status_code} {resp.text}")
            return False
        except Exception as e:
            log_warn(f"Telegram sendMessage request exception: {e}")
            return False

    def upload_document(self, file_path: pathlib.Path, caption: str = "") -> bool:
        return self.upload_documents([file_path], caption=caption)

    def upload_documents(
        self, file_paths: Sequence[pathlib.Path], caption: str = ""
    ) -> bool:
        if not self.is_configured:
            log_warn("Telegram bot token or chat ID missing; skipping document upload.")
            return False

        valid_files = [p for p in file_paths if p and p.is_file()]
        if not valid_files:
            log_error("No valid files provided for Telegram upload.")
            return False

        # If single file, direct upload
        if len(valid_files) == 1:
            return self._upload_single_file(valid_files[0], caption)

        # Multi-file check size
        total_size = sum(p.stat().st_size for p in valid_files)
        if total_size < MAX_MEDIA_GROUP_BYTES:
            if self._upload_media_group(valid_files, caption):
                return True
            log_warn("sendMediaGroup failed; falling back to individual uploads...")

        success = True
        for i, f in enumerate(valid_files):
            cap = caption if i == 0 else ""
            if not self._upload_single_file(f, cap):
                success = False
        return success

    def _upload_single_file(self, file_path: pathlib.Path, caption: str = "") -> bool:
        url = f"{self.base_url}/sendDocument"
        size_mb = file_path.stat().st_size / (1024 * 1024)
        log_info(f"Uploading {file_path.name} ({size_mb:.2f} MB) to Telegram...")

        data = {
            "chat_id": self.chat_id,
            "parse_mode": "HTML",
        }
        if caption:
            data["caption"] = caption

        try:
            with open(file_path, "rb") as f:
                files = {"document": (file_path.name, f)}
                resp = requests.post(url, data=data, files=files, timeout=600)
            if resp.status_code == 200 and resp.json().get("ok"):
                log_success(f"Uploaded {file_path.name} to Telegram successfully.")
                return True
            log_error(
                f"Telegram upload failed for {file_path.name}: {resp.status_code} {resp.text}"
            )
            return False
        except Exception as e:
            log_error(f"Telegram upload error for {file_path.name}: {e}")
            return False

    def _upload_media_group(
        self, files: Sequence[pathlib.Path], caption: str = ""
    ) -> bool:
        url = f"{self.base_url}/sendMediaGroup"
        media_list = []
        open_files = []
        files_dict = {}

        try:
            for idx, fpath in enumerate(files):
                file_key = f"file{idx}"
                item = {
                    "type": "document",
                    "media": f"attach://{file_key}",
                }
                if idx == 0 and caption:
                    item["caption"] = caption
                    item["parse_mode"] = "HTML"
                media_list.append(item)

                fp = open(fpath, "rb")
                open_files.append(fp)
                files_dict[file_key] = (fpath.name, fp)

            data = {
                "chat_id": self.chat_id,
                "media": json.dumps(media_list),
            }

            log_info(f"Uploading bundled artifacts ({len(files)} files) to Telegram...")
            resp = requests.post(url, data=data, files=files_dict, timeout=600)
            if resp.status_code == 200 and resp.json().get("ok"):
                log_success("All build artifacts uploaded together to Telegram!")
                return True
            log_warn(f"sendMediaGroup returned {resp.status_code}: {resp.text}")
            return False
        except Exception as e:
            log_warn(f"sendMediaGroup error: {e}")
            return False
        finally:
            for fp in open_files:
                fp.close()
