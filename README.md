# kbuild (`kb`)

Fast, modular Android kernel build and packaging CLI written in Python.

`kbuild` automates the entire Android kernel compilation workflow: managing toolchains (Neutron Clang), injecting integrations (KernelSU, NoMount), generating DTBO images, packaging flashable AnyKernel3 zip files, and dispatching Telegram notifications with automatic GoFile fallback.

---

## Features

- **Automated Toolchain Management**: Automatically fetches, verifies, and updates the latest [Neutron Clang](https://github.com/Neutron-Toolchains/clang-build-catalogue) release or falls back to system Clang.
- **Smart Defconfig Resolution**: Auto-expands device names into base defconfig and device configs (e.g., `kb . selene` auto-applies `vendor/mt6768_defconfig` and `vendor/selene.config`).
- **KernelSU & NoMount Injections**: One-flag injection of KernelSU and NoMount directly into kernel source trees, with post-injection `olddefconfig` synchronization and clean teardown.
- **AnyKernel3 Packaging**: Automatically packages compiled `Image` / `Image.gz-dtb` and generated `dtbo.img` into a flashable AnyKernel3 zip.
- **Smart Telegram Notifications**:
  - Real-time build status updates powered by `python-telegram-bot`.
  - Targeted compiler and linker error extraction on build failure with the full `.log` file attached.
  - Automatic fallback to [GoFile](https://gofile.io) when flashable zip files exceed Telegram's 48 MB upload limit.
  - Environment variable overrides (`TELEGRAM_CHAT_ID`, `TELEGRAM_BOT_TOKEN`, `CHAT_ID`, etc.) for seamless CI/CD automation.
- **Configuration Management**: Persistent settings stored in `~/.kbuild/config.json` (0600 permissions) powered by `configmanager`, supporting project-local overrides (`.kb.json`).
- **Structured Logging**: Clean terminal output with `loguru` and `rich` formatting.

---

## Requirements

- Linux (x86_64 or aarch64)
- Python `>= 3.12`
- Standard kernel compilation dependencies (`git`, `make`, `bc`, `bison`, `flex`, `libssl-dev`, etc.)

---

## Installation

### One-Line Install (Recommended)

```bash
curl -sSL https://raw.githubusercontent.com/mt6768-S/kernel-builder-script/main/scripts/install.sh | bash
```

### From Source

```bash
git clone https://github.com/mt6768-S/kernel-builder-script.git
cd kernel-builder-script

# Install in editable mode
pip install -e .
```

Or run the local installer:
```bash
./scripts/install.sh
# or: python main.py
```

This creates a dedicated virtual environment in `~/.kbuild/venv` and symlinks `kb` to `~/.local/bin/kb`.

---

## CLI Usage

Run `kb` by specifying the kernel path (use `.` for the current directory) and the target device or defconfig:

```bash
# Build target device (auto-applies vendor/mt6768_defconfig + vendor/selene.config)
kb . selene

# If you are already inside the kernel source directory:
kb selene

# Clean build with KernelSU and custom zip prefix
kb . selene --clean --ksu --prefix=Skyron

# Multi-threaded build with NoMount
kb . selene --nomount -j16

# Build with explicit defconfig paths
kb . vendor/mt6768_defconfig vendor/selene.config

# Build without Telegram or GoFile uploads
kb . selene --no-telegram --no-gofile
```

### CLI Options

| Argument / Flag | Description |
| :--- | :--- |
| `[kernel_path]` | Path to kernel source tree (e.g. `.` for current directory) |
| `<device / defconfig...>` | Target device (e.g. `selene`) or defconfig make targets |
| `-j, --jobs <N>` | Number of parallel build threads (default: CPU core count) |
| `--clean, --no-clean` | Clean build directory before compilation (`make mrproper`) |
| `--ksu, --no-ksu` | Enable/disable KernelSU injection |
| `--ksu-target <target>` | KernelSU branch, tag, or commit (default: `master`) |
| `--nomount, --no-nomount`| Enable/disable NoMount injection |
| `--nomount-target <target>`| NoMount branch, tag, or commit (default: `dev`) |
| `--telegram, --no-telegram` | Toggle Telegram notifications & artifact uploads |
| `--gofile, --no-gofile` | Toggle GoFile artifact uploads |
| `--prefix <prefix>` | AnyKernel3 zip filename prefix (default: `Skyron`) |
| `--clang <path>` | Path to custom Clang toolchain |
| `--ak3 <path>` | Path to custom AnyKernel3 template directory |
| `--cleanup` | Clean up KernelSU and NoMount modifications without building |

---

## Commands

```bash
# View or update persistent settings
kb config
kb config telegram=true gofile=true jobs=8
kb config reset

# Show toolchain, cache, and system status
kb info

# Check environment health, dependencies, and permissions
kb doctor

# Pre-download Neutron Clang and AnyKernel3
kb setup

# Check and update Neutron Clang to the latest release
kb update-clang

# Update kbuild to the latest git commit and sync venv
kb update

# Remove kbuild and clean shell integration
kb uninstall

# Display version
kb version
```

---

## Configuration

Settings are saved in `~/.kbuild/config.json` with strict `0600` file permissions:

```json
{
  "telegram": true,
  "gofile": false,
  "clean": true,
  "ksu": false,
  "nomount": false,
  "jobs": null,
  "cc": null,
  "zip_prefix": "Skyron",
  "host": null,
  "user": null,
  "bot_token": null,
  "chat_id": null,
  "ak3_repo": "https://github.com/mt6768-S/AnyKernel3",
  "ksu_target": "master",
  "default_defconfig": "vendor/mt6768_defconfig"
}
```

### Environment Variable Overrides

For CI/CD workflows, settings can be passed or overridden dynamically:

| Variable | Description |
| :--- | :--- |
| `TELEGRAM_CHAT_ID`, `CHAT_ID`, `TG_CHAT_ID`, `TG_CHAT` | Target Telegram Chat / Channel ID |
| `TELEGRAM_BOT_TOKEN`, `BOT_TOKEN`, `TG_BOT_TOKEN`, `TG_TOKEN` | Telegram Bot API Token |
| `KBUILD_DIR` | Custom root directory for kbuild state (default: `~/.kbuild`) |

You can also place a `.kb.json` file in the root of your kernel source tree to override settings on a per-project basis.

---

## Testing

Run the test suite using `pytest`:

```bash
pytest
```

---

## License

This project is licensed under the [GNU General Public License v3.0](LICENSE).
