"""
Module entrypoint for python -m kbuild.
"""

import sys

from kbuild.cli import main

if __name__ == "__main__":
    sys.exit(main())
