# Config Manager

## Overview

Stores user configuration in `~/.kbuild/config.json` with secure `0600` permissions.

## Keys & Defaults

| Key | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `telegram` | bool | `true` | Enable/disable Telegram notifications & uploads |
| `gofile` | bool | `false` | Enable/disable GoFile uploads |
| `clean` | bool | `true` | Clean output directory before build |
| `ksu` | bool | `false` | Enable KernelSU integration |
| `ksu_target` | string | `master` | KernelSU branch/tag/commit |
| `ksu_setup` | string | `https://raw.githubusercontent.com/backslashxx/KernelSU/master/kernel/setup.sh` | KernelSU setup script URL |
| `nomount` | bool | `false` | Enable NoMount integration |
| `nomount_target` | string | `dev` | NoMount branch/tag/commit |
| `nomount_setup` | string | `https://raw.githubusercontent.com/maxsteeel/nomount/refs/heads/dev/kernel/setup.sh` | NoMount setup script URL |
| `jobs` | int \| null | `null` | Number of parallel build jobs (null = auto CPU cores) |
| `cc` | string \| null | `null` | Compiler name (defaults to clang) |
| `zip_prefix` | string | `Skyron` | Output zip filename prefix |
| `default_defconfig` | string | `vendor/mt6768_defconfig` | Default defconfig when none supplied |
| `host` | string \| null | `null` | Hostname shown in build info |
| `user` | string \| null | `null` | Username shown in build info |
| `bot_token` | string \| null | `null` | Telegram Bot Token |
| `chat_id` | string \| null | `null` | Telegram Chat ID |
| `ak3_repo` | string | `https://github.com/mt6768-S/AnyKernel3` | AnyKernel3 repository URL |
