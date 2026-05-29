#!/usr/bin/env python3
"""Command Vault - Developer Command Operating System MVP."""

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
        f"Command Vault is missing Python package '{missing}'.\n"
        "Install dependencies with: pip3 install -r requirements.txt",
        file=sys.stderr,
    )
    sys.exit(1)

from command_vault_core.cli import main

if __name__ == "__main__":
    sys.exit(main())
