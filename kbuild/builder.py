"""
Core kernel build engine for kbuild.
Executes the compilation pipeline, integrates KernelSU/NoMount, packages AnyKernel3,
and coordinates notifications and uploads.
"""

from __future__ import annotations

import argparse
import datetime
import getpass
import html
import os
import pathlib
import re
import shutil
import socket
import subprocess
import sys
import time
import uuid
from collections.abc import Sequence
from typing import Any

from loguru import logger

from kbuild import console
from kbuild.ak3 import AnyKernelManager
from kbuild.dtbo import generate_dtbo_image
from kbuild.errors import BuildError, PreflightError
from kbuild.ksu import KernelSUManager, extract_ksu_owner
from kbuild.log_parser import extract_build_errors
from kbuild.nomount import NoMountManager
from kbuild.settings import KbuildConfig, load_config
from kbuild.toolchain import ToolchainManager
from kbuild.upload.gofile import GoFileUploader
from kbuild.upload.telegram import TelegramUploader


def resolve_defconfigs(
    source_dir: pathlib.Path, raw_configs: Sequence[str]
) -> list[str]:
    """Expands defconfig arguments into valid make target list."""
    if not raw_configs:
        return []

    if len(raw_configs) > 1:
        return list(raw_configs)

    single_cfg = raw_configs[0].strip()
    dev = (
        single_cfg.replace("vendor/", "")
        .replace("_defconfig", "")
        .replace(".config", "")
        .strip()
    )

    configs_dir = source_dir / "arch" / "arm64" / "configs"
    vendor_dir = configs_dir / "vendor"

    if (vendor_dir / "mt6768_defconfig").is_file():
        if (vendor_dir / f"{dev}.config").is_file():
            return ["vendor/mt6768_defconfig", f"vendor/{dev}.config"]
        elif (vendor_dir / single_cfg).is_file():
            return ["vendor/mt6768_defconfig", f"vendor/{single_cfg}"]
        elif single_cfg in ("vendor/mt6768_defconfig", "mt6768_defconfig"):
            return ["vendor/mt6768_defconfig"]
        elif (vendor_dir / f"{dev}_defconfig").is_file():
            return [f"vendor/{dev}_defconfig"]

    if (configs_dir / f"{dev}_defconfig").is_file():
        return [f"{dev}_defconfig"]

    if (vendor_dir / f"{dev}_defconfig").is_file():
        return [f"vendor/{dev}_defconfig"]

    if (vendor_dir / f"{dev}.config").is_file():
        if (vendor_dir / "mt6768_defconfig").is_file():
            return ["vendor/mt6768_defconfig", f"vendor/{dev}.config"]
        return [f"vendor/{dev}.config"]

    if (configs_dir / single_cfg).is_file():
        return [single_cfg]

    if (vendor_dir / "mt6768_defconfig").is_file():
        return ["vendor/mt6768_defconfig", f"vendor/{dev}.config"]

    if not single_cfg.endswith("_defconfig") and not single_cfg.endswith(".config"):
        return [f"{single_cfg}_defconfig"]

    return [single_cfg]


def extract_device_name(defconfigs: Sequence[str]) -> str:
    """Extracts a concise device identifier from the defconfig list."""
    if not defconfigs:
        return "generic"
    for cfg in reversed(defconfigs):
        name = pathlib.Path(cfg).name
        name = re.sub(r"(_defconfig|\.config)$", "", name)
        if name and name != "mt6768":
            return name
    return "mt6768"


class KernelBuilder:
    def __init__(
        self, parsed_flags: argparse.Namespace, positional_args: Sequence[str]
    ):
        self.flags = parsed_flags
        self.raw_args = list(positional_args)
        self.config: KbuildConfig = load_config()

        # Flags override configuration
        self.clean = (
            parsed_flags.clean if parsed_flags.clean is not None else self.config.clean
        )
        self.ksu_enabled = (
            parsed_flags.ksu if parsed_flags.ksu is not None else self.config.ksu
        )
        self.ksu_target = parsed_flags.ksu_target or self.config.ksu_target
        self.nomount_enabled = (
            parsed_flags.nomount
            if parsed_flags.nomount is not None
            else self.config.nomount
        )
        self.nomount_target = parsed_flags.nomount_target or self.config.nomount_target
        self.telegram_enabled = (
            parsed_flags.telegram
            if parsed_flags.telegram is not None
            else self.config.telegram
        )
        self.gofile_enabled = (
            parsed_flags.gofile
            if parsed_flags.gofile is not None
            else self.config.gofile
        )
        self.dtbo_enabled = self.config.dtbo
        self.jobs = parsed_flags.jobs or self.config.jobs or os.cpu_count() or 4
        self.cc = parsed_flags.cc or self.config.cc or "clang"
        self.prefix = parsed_flags.prefix or self.config.zip_prefix
        self.cleanup_only = parsed_flags.cleanup

        self.source_dir = self._resolve_source_dir()
        self.defconfigs = self._resolve_defconfig_list()
        self.device = extract_device_name(self.defconfigs)
        self.build_hash = uuid.uuid4().hex[:8]
        self.compiler_ver = "clang"
        self.linux_version = self._get_linux_version()

        self.ksu_mgr = KernelSUManager(
            self.source_dir, self.config.ksu_setup, self.ksu_target
        )
        self.nomount_mgr = NoMountManager(
            self.source_dir, self.config.nomount_setup, self.nomount_target
        )

        self.telegram = TelegramUploader(self.config.bot_token, self.config.chat_id)
        self.gofile = GoFileUploader()
        self.ak3_mgr = AnyKernelManager(self.config)

    def _resolve_source_dir(self) -> pathlib.Path:
        if self.raw_args:
            first_candidate = pathlib.Path(self.raw_args[0]).expanduser().resolve()
            if first_candidate.is_dir() and (first_candidate / "Makefile").is_file():
                self.raw_args.pop(0)
                return first_candidate

        cwd = pathlib.Path.cwd().resolve()
        if (cwd / "Makefile").is_file():
            return cwd

        # Look in common subdirectories
        for sub in ("kernel", "common", "android_kernel"):
            sub_dir = cwd / sub
            if sub_dir.is_dir() and (sub_dir / "Makefile").is_file():
                return sub_dir

        raise PreflightError(
            f"No kernel source tree (Makefile) found in {cwd} or supplied arguments."
        )

    def _resolve_defconfig_list(self) -> list[str]:
        if self.raw_args:
            return resolve_defconfigs(self.source_dir, self.raw_args)
        default_cfg = self.config.default_defconfig or "vendor/mt6768_defconfig"
        return resolve_defconfigs(self.source_dir, [default_cfg])

    def _get_linux_version(
        self,
        out_dir: pathlib.Path | None = None,
        env: dict[str, str] | None = None,
    ) -> str:
        # 1. Try running `make -s kernelrelease` if out_dir and env are provided
        if out_dir and env and (out_dir / ".config").is_file():
            try:
                res = subprocess.run(
                    ["make", "-s", f"O={out_dir}", "ARCH=arm64", "kernelrelease"],
                    cwd=self.source_dir,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if res.returncode == 0:
                    val = res.stdout.strip().splitlines()
                    if val and val[-1].strip():
                        return val[-1].strip()
            except Exception:
                pass

        # 2. Check compiled release file candidates
        rel_candidates = [
            (out_dir / "include" / "config" / "kernel.release") if out_dir else None,
            self.source_dir / "out" / "include" / "config" / "kernel.release",
            self.source_dir / "include" / "config" / "kernel.release",
        ]
        for c in rel_candidates:
            if c and c.is_file():
                try:
                    val = c.read_text(encoding="utf-8").strip()
                    if val:
                        return val
                except Exception:
                    pass

        # 3. Check utsrelease.h
        uts_candidates = [
            (out_dir / "include" / "generated" / "utsrelease.h") if out_dir else None,
            self.source_dir / "out" / "include" / "generated" / "utsrelease.h",
            self.source_dir / "include" / "generated" / "utsrelease.h",
        ]
        for u in uts_candidates:
            if u and u.is_file():
                try:
                    text = u.read_text(encoding="utf-8", errors="replace")
                    match = re.search(r'#define\s+UTS_RELEASE\s+"([^"]+)"', text)
                    if match:
                        return match.group(1).strip()
                except Exception:
                    pass

        # 4. Check CONFIG_LOCALVERSION in .config
        local_ver = ""
        cfg_candidates = [
            (out_dir / ".config") if out_dir else None,
            self.source_dir / "out" / ".config",
            self.source_dir / ".config",
        ]
        for cf in cfg_candidates:
            if cf and cf.is_file():
                try:
                    for line in cf.read_text(
                        encoding="utf-8", errors="replace"
                    ).splitlines():
                        if line.startswith("CONFIG_LOCALVERSION="):
                            local_ver = line.split("=", 1)[1].strip().strip('"')
                            break
                except Exception:
                    pass
                if local_ver:
                    break

        if not local_ver:
            for lv_file in sorted(self.source_dir.glob("localversion*")):
                try:
                    local_ver += lv_file.read_text(encoding="utf-8").strip()
                except Exception:
                    pass

        # 5. Parse top-level Makefile for VERSION, PATCHLEVEL, SUBLEVEL, EXTRAVERSION
        v, p, s, extra = "", "", "", ""
        mf = self.source_dir / "Makefile"
        if mf.is_file():
            try:
                for line in mf.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines():
                    if line.startswith("VERSION ="):
                        v = line.split("=", 1)[1].strip()
                    elif line.startswith("PATCHLEVEL ="):
                        p = line.split("=", 1)[1].strip()
                    elif line.startswith("SUBLEVEL ="):
                        s = line.split("=", 1)[1].strip()
                    elif line.startswith("EXTRAVERSION ="):
                        extra = line.split("=", 1)[1].strip()
                    if v and p and s and extra:
                        break
            except Exception:
                pass

        base_ver = f"{v}.{p}.{s}" if (v and p and s) else "Unknown"
        if extra:
            base_ver += extra
        if local_ver:
            base_ver += local_ver
        return base_ver

    def _notify_build_started(self) -> None:
        if self.telegram_enabled and self.telegram.is_configured:
            host = self.config.host or socket.gethostname()
            ksu_owner = (
                extract_ksu_owner(self.config.ksu_setup)
                if self.ksu_enabled
                else "NO KSU"
            )
            nomount_status = "included" if self.nomount_enabled else "not included"
            start_msg = (
                f"Building Kernel (<i>{html.escape(self.build_hash)}</i>)\n"
                f"<b>Device</b>: <b><code>{html.escape(self.device)}</code></b>\n"
                f"<b>Linux Version</b>: <b><code>{html.escape(self.linux_version)}</code></b>\n"
                f"<b>KernelSU</b>: <b><code>{html.escape(ksu_owner)}</code></b>\n"
                f"<b>NoMount</b>: <b><code>{html.escape(nomount_status)}</code></b>\n"
                f"<b>Compiler</b>: <b><code>{html.escape(self.compiler_ver)}</code></b>\n"
                f"<b>Action Host</b>: <b><code>{html.escape(host)}</code></b>\n"
                f"<b>Cores</b>: <b><code>{html.escape(str(self.jobs))}</code></b>"
            )
            self.telegram.send_message(start_msg)

    def _get_commit_hint(self) -> str:
        try:
            res = subprocess.run(
                ["git", "log", "-1", "--pretty=format:%h: %s (%cr) <%an>"],
                cwd=self.source_dir,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode == 0 and res.stdout:
                return res.stdout.strip()
        except Exception:
            pass
        return "No git commit information available"

    def run(self) -> int:
        if self.cleanup_only:
            logger.log(
                "STEP",
                "{}",
                "[CLEANUP] Cleaning up KernelSU and NoMount integrations...",
            )
            self.ksu_mgr.cleanup()
            self.nomount_mgr.cleanup()
            logger.success("{}", "Integrations cleaned up successfully.")
            return 0

        clang_dir = ToolchainManager.resolve_toolchain(self.flags.clang)
        if not clang_dir:
            raise PreflightError("Failed to resolve Clang toolchain.")

        clang_bin = (
            clang_dir / "bin" / "clang"
            if (clang_dir / "bin" / "clang").is_file()
            else pathlib.Path(shutil.which(self.cc) or self.cc)
        )
        _, self.compiler_ver = ToolchainManager.test_clang_binary(clang_bin)

        start_time = time.time()
        out_dir = self.source_dir / "out"
        log_file = pathlib.Path("/tmp") / f"kbuild_{self.build_hash}.log"

        try:
            self._execute_build(clang_dir, out_dir, log_file)
            elapsed_seconds = int(time.time() - start_time)
            build_time_str = str(datetime.timedelta(seconds=elapsed_seconds))

            # Find compiled image artifact
            boot_dir = out_dir / "arch" / "arm64" / "boot"
            artifacts: list[pathlib.Path] = []
            for candidate in ("Image.gz-dtb", "Image.gz", "Image"):
                img_path = boot_dir / candidate
                if img_path.is_file():
                    artifacts.append(img_path)
                    break

            if not artifacts:
                raise BuildError(
                    f"Build completed but no kernel image found in {boot_dir}"
                )

            # DTBO generation if enabled and available
            if self.dtbo_enabled:
                dtbo_path = generate_dtbo_image(out_dir)
                if dtbo_path:
                    artifacts.append(dtbo_path)

            # Packaging AnyKernel3
            zip_path, sha256_hex = self.ak3_mgr.package(
                artifacts=artifacts,
                device=self.device,
                prefix=self.prefix,
                explicit_ak3=self.flags.ak3,
            )

            commit_hint = self._get_commit_hint()

            # Uploads
            gofile_url: str | None = None
            if self.gofile_enabled:
                gofile_url = self.gofile.upload_file(zip_path)

            if self.telegram_enabled and self.telegram.is_configured:
                ksu_owner = (
                    extract_ksu_owner(self.config.ksu_setup)
                    if self.ksu_enabled
                    else "NO KSU"
                )
                nomount_status = "included" if self.nomount_enabled else "not included"
                success_caption = (
                    f"Build Success (<i>{html.escape(self.build_hash)}</i>)\n"
                    f"<b>Device</b>: <b><code>{html.escape(self.device)}</code></b>\n"
                    f"<b>Linux Version</b>: <b><code>{html.escape(self.linux_version)}</code></b>\n"
                    f"<b>KernelSU</b>: <b><code>{html.escape(ksu_owner)}</code></b>\n"
                    f"<b>NoMount</b>: <b><code>{html.escape(nomount_status)}</code></b>\n"
                    f"<b>Build Time</b>: <b><code>{html.escape(build_time_str)}</code></b>\n"
                    f"<b>SHA256</b>: <b><code>{html.escape(sha256_hex)}</code></b>\n"
                    f"<pre>\n{html.escape(commit_hint)}\n</pre>"
                )
                self.telegram.upload_document(
                    zip_path, caption=success_caption, gofile_url=gofile_url
                )

            logger.log(
                "STEP",
                "{}",
                f"[COMPLETE] Kernel build and packaging completed in {build_time_str}!",
            )
            console.print(f"[bold green]Artifact:[/bold green] {zip_path}")
            return 0

        except Exception as e:
            log_tail = ""
            if log_file.is_file():
                try:
                    log_tail = extract_build_errors(log_file)
                except Exception:
                    pass

            if self.telegram_enabled and self.telegram.is_configured:
                escaped_tail = html.escape(log_tail or str(e))
                fail_msg = (
                    f"Build Failed (<i>{self.build_hash}</i>)\n"
                    f"<pre>\n{escaped_tail}\n</pre>"
                )
                self.telegram.send_message(fail_msg)
                if log_file.is_file():
                    self.telegram.upload_document(log_file)

            raise
        finally:
            # Cleanup integrations if injected
            if self.ksu_mgr.injected:
                self.ksu_mgr.cleanup()
            if self.nomount_mgr.injected:
                self.nomount_mgr.cleanup()

    def _run_make_command(
        self,
        cmd: list[str],
        env: dict[str, str],
        log_handle: Any = None,
        error_context: str = "Command",
    ) -> None:
        proc = subprocess.Popen(
            cmd,
            cwd=self.source_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            errors="replace",
        )

        if proc.stdout:
            for line in proc.stdout:
                sys.stdout.write(line)
                sys.stdout.flush()
                if log_handle:
                    log_handle.write(line)
                    log_handle.flush()

        proc.wait()
        if proc.returncode != 0:
            raise BuildError(f"{error_context} failed with exit code {proc.returncode}")

    def _execute_build(
        self, clang_dir: pathlib.Path, out_dir: pathlib.Path, log_file: pathlib.Path
    ) -> None:
        logger.log(
            "STEP",
            "{}",
            f"[BUILD] Building kernel for device '{self.device}' with {self.jobs} cores...",
        )

        env = os.environ.copy()
        env["PATH"] = f"{clang_dir / 'bin'}:{env.get('PATH', '')}"
        env["ARCH"] = "arm64"
        env["SUBARCH"] = "arm64"
        env["KBUILD_BUILD_USER"] = self.config.user or getpass.getuser()
        env["KBUILD_BUILD_HOST"] = self.config.host or socket.gethostname()

        # Keep Neutron for the target, but compile host tools with a compiler
        # that is known to execute on this machine (fixdep exits with SIGILL
        # when built or run through an incompatible downloaded toolchain).
        host_clang = ToolchainManager.find_system_clang()
        base_make_args = [
            "make",
            f"O={out_dir}",
            "ARCH=arm64",
            f"CC={self.cc}",
            "LLVM=1",
            "LLVM_IAS=1",
            "LD=ld.lld",
            "AR=llvm-ar",
            "NM=llvm-nm",
            "OBJCOPY=llvm-objcopy",
            "OBJDUMP=llvm-objdump",
            "READELF=llvm-readelf",
            "STRIP=llvm-strip",
            "CROSS_COMPILE=aarch64-linux-gnu-",
            "CROSS_COMPILE_ARM32=arm-linux-gnueabi-",
            "CROSS_COMPILE_COMPAT=arm-linux-gnueabi-",
            "CLANG_TRIPLE=aarch64-linux-gnu-",
            "CONFIG_NO_ERROR_ON_MISMATCH=y",
            "TARGET_BUILD_VARIANT=user",
            "KCFLAGS=-Wno-error=default-const-init-var-unsafe -Wno-default-const-init-var-unsafe",
            f"-j{self.jobs}",
        ]
        if host_clang:
            base_make_args.append(f"HOSTCC={host_clang}")
            host_clangxx = shutil.which("clang++")
            if host_clangxx:
                base_make_args.append(f"HOSTCXX={host_clangxx}")

        if self.clean:
            logger.info("{}", f"Cleaning build directory: {out_dir}")
            if out_dir.exists():
                shutil.rmtree(out_dir, ignore_errors=True)

        out_dir.mkdir(parents=True, exist_ok=True)

        with open(log_file, "w", encoding="utf-8") as lf:
            # 1. Defconfig step (combined in a single make invocation)
            combined_configs = " ".join(self.defconfigs)
            logger.info("{}", f"Generating config from: {combined_configs}")
            defcfg_cmd = base_make_args + self.defconfigs
            self._run_make_command(
                defcfg_cmd,
                env,
                lf,
                error_context=f"Defconfig generation ({combined_configs})",
            )

            # Resolve full kernel version (e.g. 4.19.325-cip20-st20-Skyron) now that out/.config exists
            self.linux_version = self._get_linux_version(out_dir, env)

            # Send Telegram building notification after defconfig generation
            self._notify_build_started()

            # 2. KernelSU injection
            if self.ksu_enabled:
                self.ksu_mgr.inject()

            # 3. NoMount injection
            if self.nomount_enabled:
                self.nomount_mgr.inject()

            # 4. Refresh config with olddefconfig if integrations modified .config
            if self.ksu_enabled or self.nomount_enabled:
                logger.info(
                    "{}", "Refreshing kernel configuration with olddefconfig..."
                )
                olddef_cmd = base_make_args + ["olddefconfig"]
                self._run_make_command(
                    olddef_cmd, env, lf, error_context="olddefconfig"
                )
                logger.success("{}", "Kernel configuration updated with olddefconfig.")

            # 5. Compilation step
            logger.info(
                "{}", f"Starting kernel compilation: {' '.join(base_make_args)}"
            )
            self._run_make_command(
                base_make_args, env, lf, error_context="Kernel compilation"
            )

        logger.success("{}", "Kernel compilation finished successfully.")
