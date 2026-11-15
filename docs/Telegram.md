# Telegram Bot Integration

This document explains how the `TelegramAPI` class works, including the Telegram Bot API endpoints used and the step-by-step logic it follows to send notifications and upload single or grouped files.

---

## Overview

`TelegramAPI` handles communication with a configured Telegram chat via a bot token. It supports sending HTML-formatted status messages and uploading build artifacts either as individual documents or bundled together into a single media group album when their combined size is under 48 MB.

---

## API Endpoints & Limits

All requests are sent to the base URL: `https://api.telegram.org/bot{bot_token}`

| Purpose | Method | Endpoint |
| :--- | :--- | :--- |
| **Send Text Notification** | `POST` | `/sendMessage` |
| **Upload Single Document** | `POST` | `/sendDocument` |
| **Upload Bundled Documents** | `POST` | `/sendMediaGroup` |

* **Media Group Size Limit:** `48 MB` (`48 * 1024 * 1024` bytes) combined across all files in a single grouped request.
* **Upload Timeout:** Up to 600 seconds (10 minutes) per upload request; 15 seconds for text messages.

---

## Step-by-Step Workflow

### 1. Initialization (`__init__`)
* **Stores credentials:** Cleans and stores the provided `bot_token` and `chat_id`.
* **Builds the base URL:** Constructs `https://api.telegram.org/bot{bot_token}` if a valid token is present. If either credential is missing, all subsequent actions exit early and return `False`.

### 2. Sending Text Messages (`send_message`)
Sends a formatted text notification to the target chat.

* **Prepares the payload:** Sets `chat_id`, `text`, `parse_mode="HTML"`, and `disable_web_page_preview="true"`.
* **Dispatches the request:** Sends a `POST` request to `/sendMessage`.
* **Checks the response:** Parses the returned JSON and returns `True` if `"ok": true`, or logs a warning and returns `False` on failure.

### 3. Preparing a Single Document (`upload_document`)
A convenience wrapper for uploading one file.

* **Delegates to batch uploader:** Wraps the single file path into a one-item list and passes it along with the optional `caption` to `upload_documents`.

### 4. Routing & Uploading Files (`upload_documents`)
Determines the best delivery method based on the number of valid files and their combined size:

1. **Validates credentials & files:** Confirms both `bot_token` and `chat_id` exist, then filters the input list to keep only files that exist on disk.
2. **Calculates total size:** Sums the file sizes (in bytes) of all valid files.
3. **Selects the upload strategy:**
   * **Single file:** If only 1 file is provided, sends it directly via `_send_file_direct`.
   * **Multiple files under 48 MB:** Attempts to bundle all files into a single album message using `_upload_media_group`. If the grouped upload fails, it logs a warning and automatically falls back to sending each file one by one.
   * **Multiple files 48 MB or larger:** Skips grouping and uploads each file sequentially via `_send_file_direct`, attaching the `caption` only to the first file.
4. **Returns overall status:** Returns `True` only if every file in the batch was uploaded successfully.

### 5. Direct Single-File Upload (`_send_file_direct`)
Uploads one file as a standard Telegram document attachment.

* **Builds multipart payload:** Sends a `POST` (`multipart/form-data`) request to `/sendDocument` containing `chat_id`, the `document` binary, and `parse_mode="HTML"`.
* **Formats caption:** If a `caption` is provided, wraps it inside `<pre>...</pre>` tags for monospace formatting.
* **Verifies completion:** Checks the response for `"ok":true`, logs success or failure, and returns a boolean result.

### 6. Bundled Album Upload (`_upload_media_group`)
Sends multiple files together inside a single Telegram message bubble.

* **Maps file attachments:** Creates a JSON `media` array where each entry has `"type": "document"` and points to an attached form field (`attach://file0`, `attach://file1`, etc.).
* **Attaches caption to the first item:** If a `caption` is provided, attaches `<pre>{caption}</pre>` with `parse_mode="HTML"` to the first item (`file0`) so Telegram displays it as the album's caption.
* **Dispatches the bundle:** Sends a `POST` (`multipart/form-data`) request to `/sendMediaGroup` containing `chat_id`, the `media` JSON manifest, and all corresponding binary file fields (`file0`, `file1`, ...).
* **Verifies completion:** Returns `True` if `"ok":true` is returned; otherwise returns `False` so `upload_documents` can trigger the sequential fallback.