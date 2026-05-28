#!/usr/bin/env python3
"""Forge - Developer Command Operating System MVP."""

import sys

try:
    import questionary
    import yaml
    import rapidfuzz
    import prompt_toolkit
    import rich
except ModuleNotFoundError as exc:
    missing = exc.name or "dependency"
    print(
        f"Forge is missing Python package '{missing}'.\n"
        "Install dependencies with: pip3 install -r requirements.txt",
        file=sys.stderr,
    )
    sys.exit(1)

from forge_core.cli import main

if __name__ == "__main__":
    sys.exit(main())
