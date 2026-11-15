# Telegram Bot Integration

This document explains how `TelegramUploader` uses
[`python-telegram-bot`](https://pypi.org/project/python-telegram-bot/) to send
notifications and upload single or grouped build artifacts.

---

## Overview

`TelegramUploader` handles communication with a configured Telegram chat via a
bot token. It sends HTML-formatted status messages and uploads artifacts either
as individual documents or as a single media-group album when their combined
size is under 48 MB. Files that exceed Telegram's limit, or that Telegram
rejects as too large, are uploaded to GoFile and linked in a follow-up message.

All transport, multipart encoding, and media-group formatting are handled by
`python-telegram-bot`; kbuild only builds the message text and captions.

---

## Limits

* **Media group size limit:** `48 MB` (`48 * 1024 * 1024` bytes) combined
  across all files in a grouped request.
* **Upload timeout:** 600 seconds per upload; 20 seconds for text messages.

---

## Workflow

### 1. Initialization (`__init__`)
Cleans and stores `bot_token` and `chat_id`. Either credential can be set or
overridden via environment variables (`TELEGRAM_CHAT_ID`, `TG_CHAT_ID`,
`CHAT_ID`, or `TG_CHAT` for the chat; `TELEGRAM_BOT_TOKEN`, `TG_BOT_TOKEN`,
`BOT_TOKEN`, or `TG_TOKEN` for the bot token). If either credential is
missing, every action exits early and returns `False`.

### 2. Sending Text Messages (`send_message`)
Runs an async `Bot` context manager and calls `bot.send_message` with
`parse_mode=HTML` and link previews disabled. `TelegramError` and unexpected
exceptions are logged and reported as `False`.

### 3. Preparing a Single Document (`upload_document`)
Convenience wrapper that delegates to `upload_documents` with a one-item list.

### 4. Routing & Uploading Files (`upload_documents`)
1. **Validates credentials & files:** Confirms credentials exist and filters
   the input to files that exist on disk.
2. **Single file:** Uploads via `_upload_single_file`.
3. **Multiple files under 48 MB:** Calls `_upload_media_group`
   (`bot.send_media_group` with `InputMediaDocument` entries). If the group
   upload fails, it falls back to uploading each file individually.
4. **Multiple files 48 MB or larger:** Uploads each file sequentially, placing
   the caption only on the first one.
5. Returns `True` only if every file was delivered (directly or via GoFile).

### 5. Direct Single-File Upload (`_upload_single_file`)
Calls `bot.send_document` with the file handle, explicit filename, optional
HTML caption, and extended upload timeouts. If a `gofile_url` is supplied, the
GoFile link is appended to the caption so it stays inside the Build Success
message. If the file exceeds 48 MB or Telegram replies `BadRequest: file is
too big`, the GoFile fallback uploads (or reuses) the file and sends the
success caption with the link appended.

### 6. Bundled Album Upload (`_upload_media_group`)
Builds `InputMediaDocument` entries from open file handles, attaches the
caption to the first item, and calls `bot.send_media_group`. A failure returns
`False` so `upload_documents` can fall back to sequential uploads.

### 7. Build Failure
`builder.py` extracts targeted compiler/linker errors with
`extract_build_errors`, sends them in a `Build Failed (<hash>)` message inside
a `<pre>` block, and uploads the full build log as a document named
`kbuild_<hash>.log`.

