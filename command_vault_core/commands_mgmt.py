import argparse
import os
import re
import subprocess
import questionary
import time
from pathlib import Path
from typing import Any
from .models import console, CommandVaultCommand, COMMANDS_DIR
from .db import load_yaml, write_yaml

def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "custom"

def append_command(group: str, name: str, cmd: str, description: str = "", tags_raw: str = "", dangerous: bool = False) -> int:
    slug = slugify(group)
    path = COMMANDS_DIR / f"{slug}.yaml"
    data = load_yaml(path, {"group": group, "icon": "", "commands": []})
    if not data.get("group"):
        data["group"] = group
    data.setdefault("commands", [])
    if any(item.get("name") == name for item in data["commands"]):
        console.print(f"[red]Command already exists in {path.name}: {name}[/red]")
        return 1
    item: dict[str, Any] = {
        "name": name,
        "cmd": cmd,
        "description": description,
        "tags": [tag.strip() for tag in tags_raw.split(",") if tag.strip()],
    }
    if dangerous:
        item["dangerous"] = True
    data["commands"].append(item)
    write_yaml(path, data)
    console.print(f"[green]Added command to {path}[/green]")
    return 0

def add_command(args: argparse.Namespace) -> int:
    if args.from_history:
        return add_from_history()
    name = args.name or questionary.text("Name:").ask()
    cmd = args.cmd or questionary.text("Command:").ask()
    group = args.group or questionary.text("Group:", default="Custom").ask()
    if not name or not cmd or not group:
        console.print("[red]Name, command, and group are required.[/red]")
        return 2
    description = args.description or questionary.text("Description:", default="").ask() or ""
    tags_raw = args.tags or questionary.text("Tags (comma-separated):", default="").ask() or ""
    dangerous = bool(args.dangerous)
    if not args.dangerous and args.name is None:
        dangerous = bool(questionary.confirm("Dangerous?", default=False).ask())
    return append_command(group, name, cmd, description, tags_raw, dangerous)

def shell_history_path() -> Path | None:
    shell_name = Path(os.environ.get("SHELL", "")).name
    candidates: list[Path] = []
    if shell_name == "zsh":
        candidates.append(Path.home() / ".zsh_history")
    if shell_name == "bash":
        candidates.append(Path.home() / ".bash_history")
    candidates.extend([Path.home() / ".zsh_history", Path.home() / ".bash_history"])
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None

def parse_history_line(line: str) -> str:
    line = line.strip()
    if not line:
        return ""
    if line.startswith(": ") and ";" in line:
        line = line.split(";", 1)[1]
    return line.strip()

def add_from_history() -> int:
    history_path = shell_history_path()
    if not history_path or not history_path.exists():
        console.print("[red]No zsh or bash history file found.[/red]")
        return 1
    counts: dict[str, int] = {}
    for line in history_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        command = parse_history_line(line)
        if command:
            counts[command] = counts.get(command, 0) + 1
    choices = [
        questionary.Choice(f"{count}x  {command}", command)
        for command, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:50]
    ]
    if not choices:
        console.print("[yellow]History file did not contain importable commands.[/yellow]")
        return 1
    selected = questionary.select("Import command from history", choices=choices).ask()
    if not selected:
        return 130
    name = questionary.text("Name:", default=selected[:50]).ask()
    group = questionary.text("Group:", default="Imported").ask()
    tags = questionary.text("Tags:", default="history").ask() or "history"
    dangerous = bool(questionary.confirm("Dangerous?", default=False).ask())
    return append_command(group, name, selected, "", tags, dangerous)

def edit_group(group: str | None) -> int:
    editor = os.environ.get("EDITOR") or str(load_config().get("editor", "vim")).replace("${EDITOR:-", "").rstrip("}")
    from .db import load_config  # Late import to prevent circularity if needed, though clean
    if group:
        path = COMMANDS_DIR / f"{slugify(group)}.yaml"
        if not path.exists():
            matches = [path for path in COMMANDS_DIR.glob("*.yaml") if group.lower() in path.stem.lower()]
            if matches:
                path = matches[0]
    else:
        choices = [questionary.Choice(path.stem, path) for path in sorted(COMMANDS_DIR.glob("*.yaml"))]
        path = questionary.select("Edit command file", choices=choices).ask()
    if not path:
        return 130
    return subprocess.call([editor, str(path)])

def delete_command(command: CommandVaultCommand) -> None:
    if not command.source_file or not command.source_file.exists():
        console.print("[red]Cannot delete: Source file not found.[/red]")
        time.sleep(1.5)
        return
    if not questionary.confirm(f"Delete command '{command.name}' from {command.group}?", default=False).ask():
        return
    data = load_yaml(command.source_file, {})
    cmds = data.get("commands", [])
    data["commands"] = [c for c in cmds if c.get("name") != command.name or c.get("cmd") != command.cmd]
    write_yaml(command.source_file, data)
    console.print(f"[green]Deleted '{command.name}'.[/green]")
    time.sleep(1)
