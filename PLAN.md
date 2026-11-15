# Kernel Builder Script — Implementation Plan

> **Goal:** turn this repo from a collection of docs/stubs into a polished, installable, self-updating Android kernel build tool with one first-class CLI (`kb`), reliable packaging, uploads, and a safe installer lifecycle.

Status: **PLAN ONLY** — no implementation has started yet.

---

## 1. Confirmed Product Direction

These decisions supersede older reference-project assumptions:

- Use the new folder/package design from this plan; do not reproduce the old reference folder layout.
- Expose only `kb`. Do not install, document, or maintain `pb` aliases or compatibility commands.
- Keep Telegram integration in Python, based on the existing Telegram API helper approach. `curl` must not be a Telegram runtime dependency.
- Support KernelSU and NoMount as independent optional integrations; both may be enabled together. Execution order is KernelSU, then NoMount. A failed integration aborts the build.
- KernelSU setup script URL is configured in `config.json` (default: `https://raw.githubusercontent.com/backslashxx/KernelSU/master/kernel/setup.sh`).
- KernelSU target is configurable (`ksu_target`), default `master`; the user may set any branch, commit, or tag. It is passed to the setup script.
- KernelSU cleanup is **always** performed with `--cleanup` after the build, including on failure.
- KernelSU owner/tag in the Telegram message is parsed from the **setup script URL** (e.g. `backslashxx`, `Mrshockwaveog`). If parsing fails, show `OK`; if KernelSU is disabled, show `NO KSU`.
- NoMount is configurable via both `config.json` (`nomount: true/false`) and CLI (`--nomount` / `--no-nomount`).
- NoMount target is configurable (`nomount_target`), default `dev`; it is passed to the setup script. Cleanup is **always** performed with `--cleanup` after the build, including on failure.
- NoMount uses `https://raw.githubusercontent.com/maxsteeel/nomount/refs/heads/dev/kernel/setup.sh` via direct `curl ... | bash -` (with target argument when set).
- AnyKernel3 uses `https://github.com/mt6768-S/AnyKernel3` by default, is pulled every build, and falls back to the cached tree with a warning if the pull fails.
- Telegram credentials live only in `config.json`; if Telegram is enabled without credentials, skip with a warning. Uploads (Telegram, GoFile) are best-effort: failure does not invalidate a successful build (exit code stays 0). GoFile is off by default.
- Telegram captions follow `docs/ExampleTexts.md`; NoMount status is `included` / `not included`.
- Packaged AnyKernel3 zips go to `/tmp` and are kept. Build-log location, naming, retention, and rotation are **deferred to the end** (provisional `/tmp`).
- Python minimum is **3.12**. Installer is Python-only (no system package installation) and updates shell startup for **bash** and **zsh**.
- Install model: clone into `~/.kbuild/app`, use `~/.kbuild/venv`; `kb update` runs `git pull` plus a dependency sync.
- Neutron Clang installs lazily on first build (also available via `kb setup` / `kb update-clang`).
- Update checking runs on every `kb` command, throttled to once per 24 hours, notify-only; channel is `main` plus release-tag notifications.
- The old `helpers/` folder is removed after its logic is ported into the new package.
- Installer, updater, config, and build pipeline are designed around the new layout without old-folder compatibility code.

All design decisions and integration defaults are fully confirmed. Ready for implementation.

## 2. Where we are today

| Area | Current state |
| --- | --- |
| `main.py` | Empty (0 bytes). No entry point. |
| `helpers/` | `gofile.py` + `mkdtboimg.py` copied from reference; `neutron_clang.py` is empty. Missing `common/config/clang/telegram/pb`. |
| `scripts/` | `install.sh`, `update.sh`, `uninstall.sh` contain **only comments** — no executable logic. |
| `docs/` | Good design notes |
| Reference project | `/home/home/Belgeler/helpers` — working `pb` v4.0.0 (974-line builder, clang manager, config, telegram, gofile). |
| Packaging | No `pyproject.toml`, no venv handling, no console-script, no tests, no CI. |
| Security | Reference `config.py` contains a **hard-coded Telegram bot token + chat ID**. This must not be ported and should be revoked. |

### Reference behaviour we keep (and improve)
- Kernel build pipeline: defconfig resolution → optional KernelSU → `make` → AnyKernel3 zip → optional DTBO → uploads.
- Neutron Clang manager with latest-release detection, CPU compatibility test (AVX / exit 132), and system-clang fallback.
- JSON config with one-time CLI overrides, local config override, `--info`, `--update-clang`.
- Telegram (text + single/album documents) and GoFile (server discovery + shared folder) uploads.

### Known issues to fix while porting
1. Hard-coded Telegram credentials (remove; config-only; tell user to rotate).
2. `~/.kbuilds` vs `~/.kbuild` inconsistency between reference and docs. We are gonna use kbuild folder
3. Shell scripts are non-functional.
4. `curl` is a runtime dependency for uploads; use Python HTTP instead.
5. Fragile string matching of JSON (`'"ok":true' in stdout`).
6. No retries, no timeouts strategy, no log redaction.
7. No signal handling: Ctrl-C leaves KernelSU injected and the logger open.
8. `pb.py` couples UI, build, packaging, upload, config, and info in one file.
9. No preflight validation (missing tools, disk space, broken source tree).
10. Unpinned/no dependency management; no reproducible install.

---

## 3. Target architecture

```
kernel-builder-script/
├── main.py                     # tiny shim -> kbuild.cli:main
├── pyproject.toml              # metadata, deps, console scripts [kb]
├── README.md                   # quick start + examples
├── PLAN.md                     # this file (kept as architecture documentation)
├── kbuild/                     # the application package
│   ├── __init__.py             # __version__ (git-describe aware)
│   ├── cli.py                  # argparse surface, flag parsing, dispatch
│   ├── paths.py                # all filesystem locations, env overrides
│   ├── console.py              # rich console, logging, tee, redaction
│   ├── config.py               # schema, load/save/migrate, local overrides
│   ├── errors.py               # typed exceptions + exit codes
│   ├── net.py                  # HTTP session, retries, downloads w/ progress
│   ├── preflight.py            # doctor: tools, disk, source, network
│   ├── defconfig.py            # shorthand/vendor resolver (configurable)
│   ├── builder.py              # KernelBuilder pipeline
│   ├── toolchain.py            # Neutron Clang + system clang + compatibility
│   ├── ak3.py                  # AnyKernel3 clone/cache + zip packaging
│   ├── dtbo.py                 # mkdtboimg wrapper + dtbo.img discovery
│   ├── ksu.py                  # KernelSU inject/cleanup (safe download+run)
│   ├── nomount.py              # NoMount inject/cleanup (safe download+run)
│   ├── info.py                 # environment/info rendering
│   ├── upload/
│   │   ├── __init__.py
│   │   ├── base.py             # Uploader protocol + result types
│   │   ├── telegram.py         # sendMessage / sendDocument / sendMediaGroup
│   │   └── gofile.py           # servers + uploadFile + folder grouping
│   ├── update.py               # update checker + self-update
│   ├── install.py              # python side of installer lifecycle
│   ├── uninstall.py            # cleanup logic
│   ├── vendor/
│   │   └── mkdtboimg.py        # vendored AOSP tool (license preserved)
│   └── templates/
│       └── shell_env.sh        # PATH/env snippet written into rc
├── scripts/
│   ├── install.sh              # thin, robust wrapper -> python -m kbuild.install
│   ├── update.sh               # wrapper -> kb update
│   └── uninstall.sh            # wrapper -> kb uninstall
├── tests/
│   ├── conftest.py
│   ├── test_defconfig.py
│   ├── test_config.py
│   ├── test_update.py
│   ├── test_packaging.py
│   ├── test_builder.py         # fake Makefile/clang, no real compile
│   └── test_uploads.py         # mocked HTTP
```

### Dependency choices (external allowed)
Runtime:
- **`rich`** — tables, progress bars, pretty errors, `NO_COLOR` aware.
- **`requests`** — HTTP with sessions, streaming uploads, retries.
- **`packaging`** — correct version comparison for updates.

Dev:
- **`pytest`**, **`pytest-mock`**, **`ruff`**, **`mypy`** (advisory).

Everything else from the stdlib (`argparse`, `pathlib`, `zipfile`, `tarfile`, `hashlib`, `json`, `tomllib`).

Minimum Python: **3.12** (test on 3.12–3.14).

---

## 4. Filesystem layout (installed)

Primary location: **`~/.kbuild`**. This is a new layout and does not restore the old `~/.kbuilds` structure.

```
~/.kbuild/
├── app/               # installed application source/package (update target)
├── venv/              # isolated interpreter + deps
├── bin/kb             # venv console script
├── env.sh             # sourceable PATH snippet (managed block in rc)
├── config.json        # user config (existing key names preserved)
├── toolchain_info.json# clang install metadata
├── clang/             # Neutron Clang
├── AnyKernel3/        # cached AK3 tree
└── cache/             # downloaded archives, update-check state
```

- **Packaged AnyKernel3 zips are written to `/tmp`.** Build-log location, naming, retention, and rotation are **deferred to the end of implementation** (provisional: `/tmp`).
- `~/.local/bin/kb` symlink to `~/.kbuild/bin/kb`.
- No `pb` symlink or compatibility command.
- Environment overrides: `KB_HOME`, `KB_NO_UPDATE_CHECK`, `KB_OFFLINE`, `NO_COLOR`.
- Local per-project override: `.kb.json` only.

---

## 5. CLI surface

```
kb <path> <device> [flags]          # build from another directory
kb <device> [flags]                 # build from inside the kernel tree
kb config [key=value ... | reset]   # view/update persistent config
kb info                             # toolchain + environment summary
kb doctor                           # preflight diagnostics
kb setup [--clang] [--ak3]          # install/refresh optional components
kb update [--check] [--force]       # self-update (notify by default)
kb update-clang [--force]           # refresh toolchain
kb uninstall [--purge]              # remove links/env; --purge removes install data
kb version | --version | -v
kb help   | --help   | -h
```

One-time build flags (do not persist):
`--clean/-c`, `--dirty`, `--telegram/--tg`, `--no-telegram`, `--gofile/--gf`,
`--no-gofile`, `--no-upload`, `--ksu/-k`, `--no-ksu`, `--nomount`, `--no-nomount`,
`--dtbo`, `--nodtbo`, `-j/--jobs N`, `--cc CMD`, `--zip-prefix P`, `--dry-run`,
`--verbose/-V`, `--quiet/-q`, `--no-update-check`.

Example:
```bash
kb mt6768 selene --clean --ksu --telegram -j16
kb android_kernel_xiaomi_mt6768 selene --gofile --nomount
kb config telegram=true jobs=16
kb doctor
```

---

## 6. Config design

- Flat JSON for the first release; no old-layout compatibility requirement.
- Dataclass with defaults + validation; unknown keys preserved but warned.
- Written atomically (temp file + `os.replace`), mode `0600` (may contain secrets).
- Secrets (`bot_token`, `chat_id`) are read from `~/.kbuild/config.json` only.
- Config is written with restrictive permissions (`0600`) and values are never printed or committed.
- **No credentials committed.** Plan explicitly includes revoking the token currently present in the reference project.

Default schema (superset of reference):

```json
{
  "telegram": false,
  "gofile": false,
  "clean": true,
  "ksu": false,
  "nomount": false,
  "no_dtbo": false,
  "jobs": null,
  "cc": null,
  "zip_prefix": "Skyron",
  "source": null,
  "host": null,
  "user": null,
  "bot_token": null,
  "chat_id": null,
  "ak3_repo": "https://github.com/mt6768-S/AnyKernel3",
  "ak3_dir": null,
  "ak3_pull_each_build": true,
  "clang_dir": null,
  "ksu_setup": "https://raw.githubusercontent.com/backslashxx/KernelSU/master/kernel/setup.sh",
  "ksu_target": "master",
  "nomount_setup": "https://raw.githubusercontent.com/maxsteeel/nomount/refs/heads/dev/kernel/setup.sh",
  "nomount_target": "dev",
  "vendor_defconfig": "vendor/mt6768_defconfig",
  "update": { "check": true, "channel": "main", "auto_apply": false },
  "build": { "artifact_dir": "/tmp", "min_free_gb": 8 }
}
```

Logging keys are intentionally omitted until logging is finalized at the end of implementation.

Deprecated keys are dropped with a warning; nested `update`/`build` defaults are deep-merged.

---

## 7. Build pipeline (`builder.py`)

Ordered, individually timed stages, streamed through one logger:

1. **Preflight** — verify source tree (`Makefile` + `arch`), tools in PATH, free disk, `clang`, writable out dir.
2. **Resolve source/device** — path heuristics from reference, normalized.
3. **Resolve defconfig** — generic + configurable vendor sandwich:
   `vendor/<base>_defconfig` + `vendor/<device>.config`; fall back to `<device>_defconfig`, exact file, etc. No hard-coded `mt6768` outside the default config value.
4. **Notify start** (Telegram) with device, kernel version, KernelSU status, NoMount status, compiler, host, jobs.
5. **Ensure AnyKernel3** — clone if missing; `git pull` every build; if the pull fails, warn and use the cached tree.
6. **Optional clean** (`rm -rf out`, forced when KernelSU or NoMount is enabled to avoid stale state).
7. **Apply defconfig** (`make ... <targets>`).
8. **KernelSU / NoMount** (if enabled): run each setup script through `curl URL | bash -s <target>` with captured output, timeout, return-code checking, and guaranteed cleanup. Abort the build if either setup fails. Both flags are independent and may be enabled together; execution order is KernelSU first, then NoMount.
   - KernelSU target comes from `ksu_target` (default `master`), passed to the setup script. Cleanup is always `curl URL | bash -s -- --cleanup`.
   - KernelSU owner is parsed from the setup script URL. Fallback: `OK`; disabled: `NO KSU`.
   - NoMount target comes from `nomount_target` (default `dev`). Cleanup is always `curl URL | bash -s -- --cleanup`.
   - NoMount Telegram status: `included` or `not included`.
9. **Compile** (`make -jN`), stream output, detect failure.
10. **Package** (see §9).
11. **Uploads** (see §10).
12. **Summary** — artifact path, size, SHA256, duration, cache state.

Cross-cutting:
- `SIGINT`/`SIGTERM` → terminate child process group, run KernelSU/NoMount cleanup, close logger, nonzero exit.
- Log location, naming, retention, and shipping are **TBD at the end** (provisional `/tmp/kernel_build_<device>_<timestamp>.log`); secrets redacted.
- On build failure, Telegram receives **only the log tail** (no helper hint).
- Exit codes: `2` usage, `3` preflight, `4` build, `5` packaging, `6` upload, `130` interrupted.

---

## 8. Toolchain (`toolchain.py`)

Port + harden `NeutronClangManager`:
- Latest release via GitHub API, redirect fallback, archive URL construction.
- `download_with_progress` via `requests` streaming, atomic `.tmp` rename, checksum when available.
- Extract `.tar.zst/.gz/.xz` (`tarfile` for gz/xz; `zstd` binary fallback for zst).
- Compatibility probe: `clang --version`, flag exit `-4/132` as “incompatible CPU”.
- Metadata in `~/.kbuild/toolchain_info.json`: tag, URL, version, compatible, installed_at, path.
- Resolution order: explicit `clang_dir` → managed clang (if compatible) → system clang → warn.
- Install lazily on first build; `kb setup` and `kb update-clang` can install/refresh explicitly.
- `kb update-clang --force` always re-downloads.

---

## 9. Packaging (`ak3.py`, `dtbo.py`)

- Locate `Image.gz-dtb` → `Image.gz` → `Image`; copy into AK3 tree.
- DTB: `boot/dtb` then first `*.dtb` under `boot/dts` (with `dtb` copy target).
- DTBO: use existing `dtbo.img`; else build from `*.dtbo` via vendored `mkdtboimg.py`; honor `--nodtbo`.
- Zip with `zipfile` (deflate, level 9), deterministic excludes (`.git`, `.github`, README, placeholder files), written to **`/tmp`** as `PREFIX-DEVICE-YYYYMMDDHHMM.zip` (default prefix `Skyron`) and kept there after the build.
- Return an artifact descriptor `{path, size, sha256, name}` reused by uploads/captions.

---

## 10. Uploads (`upload/`)

Common `Uploader` interface returning structured results; all HTTP through one retrying session (timeouts, 3 attempts, exponential backoff).

**Telegram**
- `sendMessage`, `sendDocument`, `sendMediaGroup`.
- Single file → direct; multiple < 48 MB → album with sequential fallback; ≥ 48 MB → individual.
- Parse JSON response properly (`ok == true`), surface API `description` on failure.
- Captions follow `docs/ExampleTexts.md` (start, failure, success) with `<pre>` blocks.
- Start caption shows KernelSU owner parsed from the setup URL (or `OK` / `NO KSU`) and NoMount as `included` / `not included`.
- Failure sends **only the log tail**.
- If credentials are missing while Telegram is enabled, skip with a warning.

**GoFile**
- Server discovery, upload, reuse first response `parentFolder` for grouping.
- Stream multipart upload; return download pages.
- Off by default.

Both are best-effort: an upload failure logs a warning/error and preserves the successfully built artifact; `kb` still exits successfully.

---

## 11. Installer / uninstaller / updater

### `scripts/install.sh`
Thin wrapper that detects Python ≥ 3.12 and delegates to `python3 -m kbuild.install` (bundled, testable, cross-shell). Shell only bootstraps:
1. Locate/refresh source: clone the application into `~/.kbuild/app`.
2. Create `~/.kbuild/venv`, upgrade pip, and install the package editable from `~/.kbuild/app`.
3. Create `~/.kbuild/bin/kb`, then symlink only `kb` into `~/.local/bin`.
4. Write managed `env.sh` and append an idempotent, marker-delimited block to `.bashrc` and `.zshrc` only.
5. The installer is **Python-only**; it does not install system packages. Clang and AnyKernel3 are installed later (`kb setup` or lazily on first build).
6. Non-interactive flags: `--dir`, `--repo`, `--branch`, `--force`, `--local`.
7. Never edit files without a guaranteed rollback; back up any rc file before first write.

### `scripts/uninstall.sh`
- Remove symlinks, managed rc block, then `~/.kbuild` only with `--purge` (default keeps config/clang). Build logs and zips in `/tmp` are not touched unless explicitly requested.
- Idempotent; reports what was removed.

### Auto update checker (`update.py` + `scripts/update.sh`)
- **Automatic, cheap check** on startup of every `kb` command, throttled to once per 24 h (state in `~/.kbuild/cache/update.json`), 3 s timeout, fully silent on failure, skipped for `--quiet`, CI, `KB_NO_UPDATE_CHECK`, `KB_OFFLINE`. Prints a one-line “update available” hint.
- **Manual:** `kb update --check` (compare), `kb update` (apply), `kb update --force`.
- Comparison: `git -C ~/.kbuild/app fetch` then compare local `HEAD` to `origin/main`; also compares the newest release tag to `kbuild.__version__`.
- Apply: refuse on dirty tree unless `--force`; `git pull --ff-only`; run the dependency sync (`pip install -e ~/.kbuild/app`) when `pyproject.toml` changed; print a short changelog summary.
- Channels: `main` plus release-tag notifications.
- Does **not** auto-apply (`update.auto_apply=false`).

---

## 12. Observability & UX

- Rich status: step banners, spinners, progress bars, colored success/warn/error, final summary table.
- `--verbose` streams make output unchanged; default also streams but with stage headers; `--quiet` only warnings/errors + final artifact.
- `kb doctor` table: python, venv, git, make, clang (managed/system), zstd, curl (optional now), disk free, config validity, network reachability, update status.
- `kb info` reproduces reference info (toolchain, AK3 cache, global command, active settings) using rich.

---

## 13. Testing & quality gates

- **Unit:** defconfig resolver matrix, config defaults/validation/atomic save, version comparison, update decision, zip exclude logic, caption rendering, KernelSU owner parsing, KSU/NoMount cleanup commands.
- **Integration (no compiler):** fake kernel tree with `Makefile`/`arch`/configs and a fake `clang` script; assert pipeline ordering, artifact creation, cleanup, exit codes.
- **HTTP:** mocked `requests` for Telegram/GoFile; assert album fallback, missing-credential skip, and error paths.
- **Signals:** simulate interrupt; assert KernelSU/NoMount cleanup and logger close.
- **CI:** GitHub Actions — `ruff check`, `ruff format --check`, `pytest` on 3.12/3.13/3.14; optional `mypy`.
- **Manual smoke:** `kb doctor`, `kb --version`, `kb config`, `--dry-run` on a real tree.

Acceptance criteria:
- Fresh `scripts/install.sh` produces a working `kb` in a clean shell.
- `kb doctor` passes on a prepared host.
- A fake-tree dry run completes all stages except compile.
- Real reference build produces the expected `/tmp/Skyron-<device>-<timestamp>.zip`.
- `/tmp` artifacts and logs remain after a successful build.
- KernelSU and NoMount targets/cleanup run correctly; owner parsing matches the setup URL.
- `scripts/uninstall.sh --purge` fully removes install.
- Updater reports and applies a test commit in a throwaway clone.

---

## 14. Phased execution checklist

**Phase 0 — Safety & scaffold**
- [ ] Rotate/remove leaked Telegram bot token from reference; never commit secrets.
- [ ] `pyproject.toml` (Python ≥3.12), package skeleton, versioning, `.gitignore` update.
- [ ] `console.py`, `errors.py`, `paths.py`, `net.py`.

**Phase 1 — Config + CLI core**
- [ ] Config dataclass, load/save/validate, local overrides, config-only secrets.
- [ ] argparse CLI skeleton + help/version/config/info/doctor dispatch.
- [ ] Automatic update-check hook (throttled).

**Phase 2 — Toolchain + preflight**
- [ ] Port/harden Neutron Clang manager; `update-clang`.
- [ ] Preflight checks and `kb doctor` rendering.

**Phase 3 — Build engine**
- [ ] Defconfig resolver (generic + configurable vendor base).
- [ ] Builder pipeline with staging, signals, exit codes; logging plumbing left pluggable.
- [ ] KernelSU module (target arg, owner-from-URL parse, `--cleanup`, guaranteed cleanup).
- [ ] NoMount module (target arg, `--cleanup`, guaranteed cleanup).
- [ ] Remove old `helpers/` folder after the port is verified.

**Phase 4 — Packaging**
- [ ] AK3 clone/cache + pull every build (fallback to cache with warning); DTBO generation; deterministic zip in `/tmp`; artifact descriptor.

**Phase 5 — Uploads**
- [ ] `requests`-based Telegram (message, document, album fallback, missing-credential skip).
- [ ] GoFile (server discovery, grouped upload, off by default).
- [ ] Exact `docs/ExampleTexts.md` captions, KernelSU owner/`OK`/`NO KSU`, NoMount `included`/`not included`, failure log tail only.

**Phase 6 — Installer lifecycle**
- [ ] `kbuild/install.py`, `uninstall.py`, `shell_env.sh` template (bash + zsh).
- [ ] Executable `scripts/install.sh`, `update.sh`, `uninstall.sh` wrappers.
- [ ] Clone + venv + editable install; `kb update` = `git pull` + dependency sync.
- [ ] Idempotent rc handling; Python-only installer.

**Phase 7 — Tests, CI, docs**
- [ ] Unit + integration tests, mocked HTTP, CI workflow on Python 3.12–3.14.
- [ ] README quick start, config reference, troubleshooting; update `docs/*.md` to new layout.

**Phase 8 — Release hardening**
- [ ] Version tag, changelog, `kb update` validated against main and a release tag.
- [ ] **Finalize logging:** exact log location, filename, retention/rotation, and /tmp cleanup policy.

---

## 15. Confirmed Decisions

All planning decisions are settled:

1. **Install dir:** `~/.kbuild` (new layout; no old `~/.kbuilds` compatibility).
2. **Command:** `kb` only; no `pb`.
3. **Dependencies:** `rich`, `requests`, `packaging`; Python **3.12+**.
4. **Installer:** Python-only; clone `~/.kbuild/app`, `~/.kbuild/venv`, editable install, `kb` symlink, bash + zsh rc blocks.
5. **Updates:** check on every `kb` command, throttled 24 h, notify-only, `main` + tag notifications; `kb update` = `git pull` + dependency sync.
6. **Builder:** generic with `vendor/mt6768_defconfig` as the configurable default profile.
7. **Output:** zip prefix `Skyron`; zips go to `/tmp` and are kept. Logging location/retention is finalized at the end.
8. **Uploads:** best-effort; upload failures keep exit code 0. Telegram credentials config-only; missing credentials skip with a warning. GoFile off by default.
9. **Telegram captions:** exact `docs/ExampleTexts.md`; failure sends only the log tail. NoMount is `included` / `not included`.
10. **KernelSU:** default setup URL `backslashxx`, configurable `ksu_target` (default `master`), owner parsed from the setup URL (`OK` fallback, `NO KSU` when disabled), cleanup always with `--cleanup`.
11. **NoMount:** configurable via config and `--nomount`, default target `dev`, direct pipe-to-bash, cleanup always with `--cleanup`.
12. **Integrations:** both off by default, independent, both allowed, KernelSU first; setup failure aborts the build.
13. **AnyKernel3:** clone once to cache, `git pull` every build, fall back to cache with a warning if the pull fails.
14. **Clang:** Neutron Clang installed lazily on first build; system-clang fallback; explicit `kb setup` / `kb update-clang`.
15. **Old `helpers/`:** removed after the port is verified. **`PLAN.md`:** kept in the repo.

Planning is complete. Implementation can start at Phase 0.
