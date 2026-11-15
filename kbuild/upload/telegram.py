"""
Telegram integration for kbuild, backed by python-telegram-bot.

Sends status messages, logs, and build artifacts; uploads that exceed the
Telegram size limit fall back to GoFile.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import pathlib
from collections.abc import Coroutine, Sequence
from typing import Any

from loguru import logger
from telegram import Bot, InputMediaDocument, LinkPreviewOptions
from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError

MAX_MEDIA_GROUP_BYTES = 48 * 1024 * 1024  # 48 MB

_MESSAGE_TIMEOUT = 20
_UPLOAD_TIMEOUT = 600
_CONNECT_TIMEOUT = 30


class TelegramUploader:
    def __init__(self, bot_token: str | None = None, chat_id: str | None = None):
        env_token = (
            os.environ.get("TELEGRAM_BOT_TOKEN")
            or os.environ.get("TG_BOT_TOKEN")
            or os.environ.get("BOT_TOKEN")
            or os.environ.get("TG_TOKEN")
        )
        env_chat = (
            os.environ.get("TELEGRAM_CHAT_ID")
            or os.environ.get("TG_CHAT_ID")
            or os.environ.get("CHAT_ID")
            or os.environ.get("TG_CHAT")
        )

        resolved_token = (
            env_token.strip()
            if env_token and env_token.strip()
            else (bot_token or "").strip()
        )
        resolved_chat = (
            env_chat.strip()
            if env_chat and env_chat.strip()
            else (chat_id or "").strip()
        )

        self.bot_token = resolved_token
        self.chat_id = resolved_chat

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    @staticmethod
    def _run(coroutine: Coroutine[Any, Any, Any]) -> Any:
        return asyncio.run(coroutine)

    @staticmethod
    def _is_too_big(error: BadRequest) -> bool:
        text = (error.message or "").lower()
        return "too big" in text or "too large" in text

    @staticmethod
    def _gofile_note(url: str) -> str:
        return f'<b>📦 Download (GoFile)</b>: <a href="{url}">{url}</a>'

    @classmethod
    def _caption_with_gofile(cls, caption: str, gofile_url: str | None) -> str:
        if not gofile_url:
            return caption
        note = cls._gofile_note(gofile_url)
        return f"{caption}\n\n{note}" if caption else note

    async def _send_message(self, text: str) -> None:
        async with Bot(self.bot_token) as bot:
            await bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
                read_timeout=_MESSAGE_TIMEOUT,
                write_timeout=_MESSAGE_TIMEOUT,
                connect_timeout=_CONNECT_TIMEOUT,
            )

    async def _send_document(self, file_path: pathlib.Path, caption: str) -> None:
        async with Bot(self.bot_token) as bot:
            with open(file_path, "rb") as document:
                await bot.send_document(
                    chat_id=self.chat_id,
                    document=document,
                    filename=file_path.name,
                    caption=caption or None,
                    parse_mode=ParseMode.HTML,
                    read_timeout=_UPLOAD_TIMEOUT,
                    write_timeout=_UPLOAD_TIMEOUT,
                    connect_timeout=_CONNECT_TIMEOUT,
                )

    async def _send_media_group(
        self, files: Sequence[pathlib.Path], caption: str
    ) -> None:
        with contextlib.ExitStack() as stack:
            media = [
                InputMediaDocument(
                    media=stack.enter_context(open(fpath, "rb")),
                    filename=fpath.name,
                    caption=caption if idx == 0 and caption else None,
                    parse_mode=ParseMode.HTML,
                )
                for idx, fpath in enumerate(files)
            ]
            async with Bot(self.bot_token) as bot:
                await bot.send_media_group(
                    chat_id=self.chat_id,
                    media=media,
                    read_timeout=_UPLOAD_TIMEOUT,
                    write_timeout=_UPLOAD_TIMEOUT,
                    connect_timeout=_CONNECT_TIMEOUT,
                )

    def send_message(self, text: str) -> bool:
        if not self.is_configured:
            logger.warning(
                "{}", "Telegram bot token or chat ID missing; skipping message."
            )
            return False

        try:
            self._run(self._send_message(text))
        except TelegramError as e:
            logger.warning("{}", f"Telegram sendMessage failed: {e}")
            return False
        except Exception as e:
            logger.warning("{}", f"Telegram sendMessage request exception: {e}")
            return False
        return True

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

        if len(valid_files) == 1:
            return self._upload_single_file(valid_files[0], caption, gofile_url)

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

        base = caption or f"<b>{file_path.name}</b> ({size_mb:.1f} MB)"
        return self.send_message(self._caption_with_gofile(base, download_url))

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

        logger.info(
            "{}", f"Uploading {file_path.name} ({size_mb:.2f} MB) to Telegram..."
        )
        upload_caption = self._caption_with_gofile(caption, gofile_url)
        try:
            self._run(self._send_document(file_path, upload_caption))
        except BadRequest as e:
            if self._is_too_big(e):
                logger.warning(
                    "{}",
                    f"Telegram rejected {file_path.name} due to file size limit. "
                    "Falling back to GoFile...",
                )
                return self._fallback_gofile_upload(
                    file_path, caption, gofile_url=gofile_url
                )
            logger.error("{}", f"Telegram upload failed for {file_path.name}: {e}")
            return False
        except TelegramError as e:
            logger.error("{}", f"Telegram upload failed for {file_path.name}: {e}")
            return False
        except Exception as e:
            logger.error("{}", f"Telegram upload error for {file_path.name}: {e}")
            return False

        logger.success("{}", f"Uploaded {file_path.name} to Telegram successfully.")
        return True

    def _upload_media_group(
        self, files: Sequence[pathlib.Path], caption: str = ""
    ) -> bool:
        logger.info(
            "{}", f"Uploading bundled artifacts ({len(files)} files) to Telegram..."
        )
        try:
            self._run(self._send_media_group(files, caption))
        except TelegramError as e:
            logger.warning("{}", f"sendMediaGroup failed: {e}")
            return False
        except Exception as e:
            logger.warning("{}", f"sendMediaGroup error: {e}")
            return False

        logger.success("{}", "All build artifacts uploaded together to Telegram!")
        return True
