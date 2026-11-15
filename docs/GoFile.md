# GoFile Upload Integration

This document explains how the `GoFileAPI` class works, including the API endpoints used and the step-by-step logic it follows to upload files to GoFile.io.

---

## Overview

`GoFileAPI` is a utility class responsible for sending single or multiple local files to GoFile and retrieving their shareable download links. When uploading multiple files in a single batch, it automatically groups them into one shared folder.

---

## API Endpoints

| Purpose | Method | Endpoint |
| :--- | :--- | :--- |
| **Fetch Available Servers** | `GET` | `https://api.gofile.io/servers` |
| **Upload File** | `POST` | `https://{server}.gofile.io/uploadFile` |

---

## Step-by-Step Workflow

### 1. Finding an Available Server (`get_upload_server`)
Before uploading any file, the system needs to know which GoFile storage server is currently available to accept data.

* **Requests the server list:** Sends a `GET` request to `https://api.gofile.io/servers` (with a standard browser `User-Agent` header) to retrieve active servers.
* **Selects a server:** Parses the response (`data.servers`) and picks the `name` of the first available server (e.g., `store1`).
* **Handles failures:** If the endpoint is unreachable, times out (after 10 seconds), or returns no servers, it logs a warning and returns `None` to abort the upload safely.

### 2. Preparing a Single File (`upload_file`)
This is a convenience action for uploading just one file.

* **Wraps the file:** Takes the single file path provided, places it into a one-item list, and passes it to `upload_files`.
* **Returns the link:** Extracts and returns the single download URL from the result list (or `None` if the upload failed).

### 3. Uploading One or Multiple Files (`upload_files`)
This is the core process that validates files, manages folder grouping, and executes the transfers.

1. **Validates local files:** Filters the input list to keep only file paths that actually exist on disk. If no valid files remain, it stops and returns an empty list.
2. **Establishes the destination:** Calls `get_upload_server` to build the target upload URL: `https://{server}.gofile.io/uploadFile`.
3. **Loops through each file:** Processes the valid files sequentially, allowing up to 300 seconds (5 minutes) per file:
   * **Uploads the file:** Sends a `POST` (`multipart/form-data`) request containing the `file` payload to the target endpoint.
   * **Creates and reuses a shared folder:** 
     * When the **first** file is uploaded, GoFile automatically creates a new folder and returns its ID in `data.parentFolder`.
     * For every subsequent file in the same batch, the request includes `folderId={parentFolder}` so all files are grouped into that same folder.
   * **Collects the download link:** Extracts `data.downloadPage` from the response, logs the generated URL, and appends it to the results list.
4. **Returns all links:** Once every file in the batch has been processed, returns the complete list of public download URLs.