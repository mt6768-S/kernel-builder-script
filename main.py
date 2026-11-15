#!/usr/bin/env python3
"""
Entrypoint for kbuild CLI.
Automatically delegates to ~/.kbuild/venv if run with system Python lacking dependencies.
"""

from __future__ import annotations

import os
import pathlib
import sys

venv_python = pathlib.Path.home() / ".kbuild" / "venv" / "bin" / "python3"
if not venv_python.is_file():
    venv_python = pathlib.Path.home() / ".kbuild" / "venv" / "bin" / "python"

if sys.prefix == sys.base_prefix:
    try:
        import configmanager  # noqa: F401
        import loguru  # noqa: F401
        import requests  # noqa: F401
        import rich  # noqa: F401
        import telegram  # noqa: F401
    except ImportError:
        if venv_python.is_file():
            os.execv(str(venv_python), [str(venv_python)] + sys.argv)
        else:
            install_script = pathlib.Path(__file__).parent / "scripts" / "install.sh"
            if install_script.is_file():
                os.execv("/bin/bash", ["bash", str(install_script)] + sys.argv[1:])

from kbuild.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
