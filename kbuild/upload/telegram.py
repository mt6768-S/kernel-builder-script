"""
Telegram API helper using the requests module for kbuild.
Sends status messages, logs, and artifacts conforming to docs/ExampleTexts.md.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Sequence

import requests
from loguru import logger

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
            logger.warning(
                "{}", "Telegram bot token or chat ID missing; skipping message."
            )
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
            logger.warning(
                "{}", f"Telegram sendMessage failed: {resp.status_code} {resp.text}"
            )
            return False
        except Exception as e:
            logger.warning("{}", f"Telegram sendMessage request exception: {e}")
            return False

    def upload_document(
        self,
        file_path: pathlib.Path,
        caption: str = "",
        gofile_url: str | None = None,
    ) -> bool:
        return self.upload_documents(
            [file_path], caption=caption, gofile_url=gofile_url
        )

    def upload_documents(
        self,
        file_paths: Sequence[pathlib.Path],
        caption: str = "",
        gofile_url: str | None = None,
    ) -> bool:
        if not self.is_configured:
            logger.warning(
                "{}", "Telegram bot token or chat ID missing; skipping document upload."
            )
            return False

        valid_files = [p for p in file_paths if p and p.is_file()]
        if not valid_files:
            logger.error("{}", "No valid files provided for Telegram upload.")
            return False

        # If single file, direct upload
        if len(valid_files) == 1:
            return self._upload_single_file(valid_files[0], caption, gofile_url)

        # Multi-file check size
        total_size = sum(p.stat().st_size for p in valid_files)
        if total_size < MAX_MEDIA_GROUP_BYTES:
            if self._upload_media_group(valid_files, caption):
                return True
            logger.warning(
                "{}", "sendMediaGroup failed; falling back to individual uploads..."
            )

        success = True
        for i, f in enumerate(valid_files):
            cap = caption if i == 0 else ""
            if not self._upload_single_file(f, cap, gofile_url):
                success = False
        return success

    def _fallback_gofile_upload(
        self,
        file_path: pathlib.Path,
        caption: str = "",
        gofile_url: str | None = None,
    ) -> bool:
        from kbuild.upload.gofile import GoFileUploader

        size_mb = file_path.stat().st_size / (1024 * 1024)
        download_url = gofile_url or GoFileUploader.upload_file(file_path)
        if not download_url:
            logger.error(
                "{}",
                f"GoFile fallback upload failed for {file_path.name} ({size_mb:.2f} MB).",
            )
            return False

        link_note = (
            f'\n\n<b>📦 Download (GoFile)</b>: <a href="{download_url}">{download_url}</a>\n'
            f"<i>(File size {size_mb:.1f} MB exceeds Telegram limit)</i>"
        )
        msg = (
            f"{caption}{link_note}"
            if caption
            else f"<b>{file_path.name}</b> ({size_mb:.1f} MB)\n{link_note.strip()}"
        )
        return self.send_message(msg)

    def _upload_single_file(
        self,
        file_path: pathlib.Path,
        caption: str = "",
        gofile_url: str | None = None,
    ) -> bool:
        size_bytes = file_path.stat().st_size
        size_mb = size_bytes / (1024 * 1024)

        if size_bytes > MAX_MEDIA_GROUP_BYTES:
            logger.warning(
                "{}",
                f"{file_path.name} ({size_mb:.2f} MB) exceeds Telegram 48 MB limit. "
                "Falling back to GoFile upload...",
            )
            return self._fallback_gofile_upload(
                file_path, caption, gofile_url=gofile_url
            )

        url = f"{self.base_url}/sendDocument"
        logger.info(
            "{}", f"Uploading {file_path.name} ({size_mb:.2f} MB) to Telegram..."
        )

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
                logger.success(
                    "{}", f"Uploaded {file_path.name} to Telegram successfully."
                )
                return True

            if resp.status_code == 400 and any(
                phrase in resp.text.lower() for phrase in ("too big", "too large")
            ):
                logger.warning(
                    "{}",
                    f"Telegram rejected {file_path.name} due to file size limit. "
                    "Falling back to GoFile...",
                )
                return self._fallback_gofile_upload(
                    file_path, caption, gofile_url=gofile_url
                )

            logger.error(
                "{}",
                f"Telegram upload failed for {file_path.name}: {resp.status_code} {resp.text}",
            )
            return False
        except Exception as e:
            logger.error("{}", f"Telegram upload error for {file_path.name}: {e}")
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

            logger.info(
                "{}", f"Uploading bundled artifacts ({len(files)} files) to Telegram..."
            )
            resp = requests.post(url, data=data, files=files_dict, timeout=600)
            if resp.status_code == 200 and resp.json().get("ok"):
                logger.success(
                    "{}", "All build artifacts uploaded together to Telegram!"
                )
                return True
            logger.warning(
                "{}", f"sendMediaGroup returned {resp.status_code}: {resp.text}"
            )
            return False
        except Exception as e:
            logger.warning("{}", f"sendMediaGroup error: {e}")
            return False
        finally:
            for fp in open_files:
                fp.close()
