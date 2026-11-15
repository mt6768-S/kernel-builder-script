# Neutron Clang Toolchain Manager

This document explains how the `NeutronClangManager` class works, including the endpoints, local paths, and step-by-step logic used to fetch, install, verify, and track the Neutron Clang compiler toolchain.

---

## Overview

`NeutronClangManager` automates the lifecycle of the Neutron Clang toolchain inside the workspace. It checks GitHub for the latest release, downloads and extracts the archive, tests whether the binary runs properly on the host machine's CPU, and records installation metadata locally.

---

## Endpoints & Local Paths

| Type | Target / Path | Purpose |
| :--- | :--- | :--- |
| **Primary API Endpoint** | `GET https://api.github.com/repos/Neutron-Toolchains/clang-build-catalogue/releases/latest` | Fetches release metadata, version tags, and asset download URLs. |
| **Fallback Endpoint** | `GET https://github.com/Neutron-Toolchains/clang-build-catalogue/releases/latest` | Resolves the latest release tag via HTTP redirect if the API fails. |
| **Toolchain Directory** | `clang` | Stores the extracted compiler binaries (`bin/clang`). |
| **Metadata File** | `info.json` | @Info.md |
| **Config File** | `config.json` | @Config.md |

---

## Step-by-Step Workflow

### 1. Validating the Compiler Binary (`test_clang_binary`)
Ensures that a Clang executable exists and can run on the current machine's hardware.

* **Checks existence:** Verifies that the binary file is present at the given path.
* **Runs a version check:** Executes the binary with `--version` (with a 5-second timeout).
* **Evaluates the result:**
  * If successful, returns `True` along with the first line of the version output.
  * If it crashes with exit code `-4` or `132`, flags it as incompatible with the host CPU (typically caused by missing AVX instructions on older processors).
  * For any other failure, returns `False` along with the error or exit code.

### 2. Fetching Latest Release Details (`get_latest_release_info`)
Determines the newest available Neutron Clang version and its download link from GitHub using a two-step strategy:

1. **Primary GitHub API Check:**
   * Sends a `GET` request to the repository's `/releases/latest` API endpoint.
   * Extracts the `tag_name` and `published_at` timestamp.
   * Scans the release `assets` list for an archive ending in `.tar.zst`, `.tar.gz`, or `.tar.xz`, capturing its filename, `browser_download_url`, and file size.
2. **HTTP Redirect Fallback:**
   * If the API request fails (e.g., due to rate limiting), it requests the public GitHub `/releases/latest` web page without following redirects.
   * Reads the `Location` header to extract the tag name from `/tag/{tag_name}` and constructs the direct `.tar.zst` download URL manually.
3. **Returns release metadata:** Outputs a structured dictionary containing the tag, asset name, download URL, publish date, and size. Raises an error if both methods fail.

### 3. Managing Local Metadata (`get_installed_info` & `save_installed_info`)
* **Reading (`get_installed_info`):** Checks if `~/.kbuild/info.json` exists and reads the saved installation details. Returns `None` if the file is missing or unreadable.
* **Saving (`save_installed_info`):** Ensures the `~/.kbuild` directory exists and writes updated toolchain metadata to `~/.kbuild/info.json`.

### 4. Installing or Updating Clang (`ensure_clang`)
Coordinates the full installation and update pipeline:

1. **Checks existing installation:** If `~/.kbuild/clang/bin/clang` already exists and `force_update` is disabled, it logs the current tag and immediately returns the directory path without hitting the network.
2. **Checks for updates:** Fetches the latest release info from GitHub. If the installed tag in `info.json` already matches the latest tag (and `force_update` is off), it skips downloading.
3. **Downloads the archive:** Downloads the release archive into `~/.kbuild/` while displaying progress.
4. **Extracts the toolchain:** Wipes any previous installation in `~/.kbuild/clang`, recreates the folder, and unpacks the archive into it (retrying with explicit Zstandard decompression if the standard extraction fails).
5. **Cleans up:** Deletes the downloaded archive file from `~/.kbuild/` to save disk space.
6. **Verifies & saves metadata:** Runs `test_clang_binary` on the newly extracted `clang` executable, writes all details (tag, URL, version string, CPU compatibility, path, and timestamp) to `~/.kbuild/info.json`, and logs the final status.

### 5. Displaying Environment Status (`show_info`)
Prints a formatted summary of the entire build environment to the console:

* **Neutron Clang:** Shows the installed tag, CPU compatibility/version status, and directory path (or warns if not installed).
* **System Clang (Fallback):** Checks if a system-wide `clang` is available on the machine and displays its path and version.
* **AnyKernel3 Cache:** Reports whether `anykernel.sh` is cached inside the AnyKernel3 directory.
* **Global Command:** Checks whether the global `kb` shortcut is linked in `~/.local/bin/kb`.
* **Active Build Settings:** Reads `~/.kbuild/config.json` and displays the current state of Telegram uploads, GoFile uploads, clean builds, KernelSU integration (including its tag if enabled), and the configured `user@host` string.