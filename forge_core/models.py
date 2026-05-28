import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from rich.console import Console

VERSION = "0.1.0"
APP_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = APP_DIR / "config.yaml"
COMMANDS_DIR = APP_DIR / "commands"
FAVORITES_PATH = APP_DIR / "favorites.json"
DB_PATH = APP_DIR / "intelligence.db"
PLACEHOLDER_RE = re.compile(r"{{\s*([^{}]+?)\s*}}")
GO_BACK = -1000

console = Console()

@dataclass
class ForgeCommand:
    name: str
    cmd: str
    group: str
    icon: str = ""
    source_file: Path | None = None
    description: str = ""
    tags: list[str] | None = None
    dangerous: bool = False
    favorite: bool = False
    aliases: list[str] | None = None

    @property
    def key(self) -> str:
        return f"{self.group}::{self.name}"

    @property
    def haystack(self) -> str:
        tags = " ".join(self.tags or [])
        aliases = " ".join(self.aliases or [])
        return f"{self.name} {self.description} {self.group} {tags} {aliases} {self.cmd}"

    @property
    def label(self) -> str:
        prefix = f"{self.icon} " if self.icon else ""
        return f"{prefix}{self.group} -> {self.name}"
