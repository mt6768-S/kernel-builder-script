"""
Command line interface for kbuild (kb).
Provides subcommands: config, info, doctor, setup, update, update-clang, uninstall, version,
or executes kernel building by default.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from collections.abc import Sequence

from loguru import logger

from kbuild import __version__, console
from kbuild.doctor import run_doctor
from kbuild.errors import KbuildError
from kbuild.info import show_info
from kbuild.settings import load_config, update_config_from_pairs
from kbuild.update import notify_if_update_available, perform_update


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kb",
        description="Fast, modular Android kernel build and packaging CLI",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "-v", "--version", action="version", version=f"kbuild {__version__}"
    )

    subparsers = parser.add_subparsers(dest="subcommand", metavar="COMMAND")

    # kb config
    subparsers.add_parser(
        "config",
        help="View or modify ~/.kbuild/config.json settings (e.g. 'kb config telegram=true')",
    )

    # kb info
    subparsers.add_parser(
        "info", help="Display environment, toolchain, and build configuration info"
    )

    # kb doctor
    subparsers.add_parser(
        "doctor", help="Run comprehensive health checks on tools and environment"
    )

    # kb setup
    subparsers.add_parser(
        "setup", help="Pre-download and configure Clang toolchain and AnyKernel3"
    )

    # kb update
    subparsers.add_parser("update", help="Update kbuild from git and sync dependencies")

    # kb update-clang
    subparsers.add_parser(
        "update-clang", help="Check and install the latest Neutron Clang release"
    )

    # kb uninstall
    subparsers.add_parser(
        "uninstall", help="Uninstall kbuild and clean up shell configuration"
    )

    # kb version
    subparsers.add_parser("version", help="Print version number and exit")

    return parser


def parse_build_arguments(args: Sequence[str]) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        prog="kb",
        description="Build and package Android kernel",
        add_help=False,
    )
    parser.add_argument(
        "--clean",
        dest="clean",
        action="store_true",
        default=None,
        help="Force clean build (mrproper)",
    )
    parser.add_argument(
        "--no-clean",
        dest="clean",
        action="store_false",
        help="Skip clean step (incremental build)",
    )

    parser.add_argument(
        "--ksu",
        dest="ksu",
        action="store_true",
        default=None,
        help="Enable KernelSU integration",
    )
    parser.add_argument(
        "--no-ksu",
        dest="ksu",
        action="store_false",
        help="Disable KernelSU integration",
    )
    parser.add_argument(
        "--ksu-target", type=str, default=None, help="KernelSU branch, tag, or commit"
    )

    parser.add_argument(
        "--nomount",
        dest="nomount",
        action="store_true",
        default=None,
        help="Enable NoMount integration",
    )
    parser.add_argument(
        "--no-nomount",
        dest="nomount",
        action="store_false",
        help="Disable NoMount integration",
    )
    parser.add_argument(
        "--nomount-target",
        type=str,
        default=None,
        help="NoMount branch, tag, or commit",
    )

    parser.add_argument(
        "--telegram",
        dest="telegram",
        action="store_true",
        default=None,
        help="Upload build output to Telegram",
    )
    parser.add_argument(
        "--no-telegram",
        dest="telegram",
        action="store_false",
        help="Disable Telegram upload",
    )

    parser.add_argument(
        "--gofile",
        dest="gofile",
        action="store_true",
        default=None,
        help="Upload build output to GoFile",
    )
    parser.add_argument(
        "--no-gofile", dest="gofile", action="store_false", help="Disable GoFile upload"
    )

    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=None,
        help="Number of parallel compilation jobs",
    )
    parser.add_argument(
        "--cc",
        type=str,
        default=None,
        help="Explicit compiler binary name (e.g. clang)",
    )
    parser.add_argument(
        "--prefix",
        type=str,
        default=None,
        help="Custom prefix for output flashable zip",
    )
    parser.add_argument(
        "--ak3",
        type=str,
        default=None,
        help="Explicit path to AnyKernel3 directory or git repo",
    )
    parser.add_argument(
        "--clang",
        type=str,
        default=None,
        help="Explicit path to Clang toolchain directory",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Clean up integrations (KernelSU/NoMount) and exit",
    )
    parser.add_argument("-h", "--help", action="store_true", help="Show help message")

    parsed, remaining = parser.parse_known_args(args)
    return parsed, remaining


def print_general_help() -> None:
    console.print(f"""[bold cyan]kbuild (kb)[/bold cyan] v{__version__} - Fast, modular Android kernel build and packaging CLI

[bold]USAGE:[/bold]
  kb [kernel_path] [defconfig...] [options]
  kb <command> [args...]

[bold]COMMANDS:[/bold]
  [cyan]config[/cyan] [key=value ...]  View or update ~/.kbuild/config.json settings
  [cyan]info[/cyan]                  Show toolchain, cache, and active settings
  [cyan]doctor[/cyan]                Check environment, required binaries, and paths
  [cyan]setup[/cyan]                 Pre-download Clang and AnyKernel3
  [cyan]update[/cyan]                Update kbuild to latest version and sync dependencies
  [cyan]update-clang[/cyan]          Check and install latest Neutron Clang
  [cyan]uninstall[/cyan]             Remove kbuild and clean shell aliases
  [cyan]version[/cyan]               Show version

[bold]BUILD OPTIONS:[/bold]
  --clean, --no-clean         Clean output directory before building
  --ksu, --no-ksu             Inject KernelSU into kernel source
  --ksu-target <target>       KernelSU target branch/tag/commit (default: master)
  --nomount, --no-nomount     Inject NoMount into kernel source
  --nomount-target <target>   NoMount target branch/tag/commit (default: dev)
  --telegram, --no-telegram   Toggle Telegram artifact upload
  --gofile, --no-gofile       Toggle GoFile artifact upload
  -j, --jobs <N>              Parallel build jobs (default: auto core count)
  --cc <compiler>             Compiler name (default: clang)
  --prefix <name>             Zip file prefix (default: Skyron)
  --ak3 <path|repo>           Explicit AnyKernel3 path or repository URL
  --clang <path>              Explicit Clang toolchain path
  --cleanup                   Clean up KernelSU and NoMount modifications without building
""")


def main(argv: Sequence[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    # Automated throttled update check notification
    notify_if_update_available()

    if not argv:
        # If no arguments provided in a kernel directory, show build prompt or general help
        if (pathlib.Path.cwd() / "Makefile").is_file():
            # In a kernel source tree, default build with default defconfig
            return dispatch_build([], argv)
        print_general_help()
        return 0

    first = argv[0].strip()

    if first in ("-h", "--help", "help"):
        print_general_help()
        return 0

    if first in ("-v", "--version", "version"):
        console.print(f"kbuild {__version__}")
        return 0

    if first == "config":
        update_config_from_pairs(list(argv[1:]))
        return 0

    if first == "info":
        show_info()
        return 0

    if first == "doctor":
        ok = run_doctor()
        return 0 if ok else 1

    if first == "setup":
        from kbuild.ak3 import AnyKernelManager
        from kbuild.toolchain import ToolchainManager

        cfg = load_config()
        ToolchainManager.ensure_clang(force=False)
        AnyKernelManager(cfg).ensure_ak3()
        logger.success("{}", "Toolchain and AnyKernel3 ready!")
        return 0

    if first == "update":
        ok = perform_update()
        return 0 if ok else 1

    if first == "update-clang":
        from kbuild.toolchain import ToolchainManager

        ToolchainManager.ensure_clang(force=True)
        return 0

    if first == "uninstall":
        from kbuild.uninstall import run_uninstall

        return run_uninstall()

    # Default command: build kernel
    return dispatch_build(list(argv), argv)


def dispatch_build(args: list[str], raw_argv: Sequence[str]) -> int:
    parsed_flags, positional = parse_build_arguments(args)

    if parsed_flags.help:
        print_general_help()
        return 0

    from kbuild.builder import KernelBuilder

    try:
        builder = KernelBuilder(parsed_flags=parsed_flags, positional_args=positional)
        return builder.run()
    except KbuildError as ke:
        logger.error("{}", str(ke))
        return ke.exit_code
    except KeyboardInterrupt:
        console.print("\n[bold red]Build interrupted by user.[/bold red]")
        return 130
    except Exception as e:
        logger.error("{}", f"Unexpected error: {e}")
        return 1
