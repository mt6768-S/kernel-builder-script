#!/usr/bin/env python3
"""
Entrypoint for kbuild CLI.
Automatically delegates to ~/.kbuild/venv if run with system Python lacking dependencies.
"""

import os
import pathlib
import sys

venv_python = pathlib.Path.home() / ".kbuild" / "venv" / "bin" / "python3"
if venv_python.is_file() and sys.prefix == sys.base_prefix:
    try:
        import requests  # noqa: F401
        import rich  # noqa: F401
    except ImportError:
        os.execv(str(venv_python), [str(venv_python)] + sys.argv)

from kbuild.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
