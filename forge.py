#!/usr/bin/env python3
"""Forge - Developer Command Operating System MVP."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

VERSION = "0.1.0"
APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.yaml"
COMMANDS_DIR = APP_DIR / "commands"
FAVORITES_PATH = APP_DIR / "favorites.json"
DB_PATH = APP_DIR / "intelligence.db"
PLACEHOLDER_RE = re.compile(r"{{\s*([^{}]+?)\s*}}")
GO_BACK = -1000


try:
    import questionary
    import yaml
    from rapidfuzz import fuzz, process
    from prompt_toolkit import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.keys import Keys
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import HSplit, Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.styles import Style
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
except ModuleNotFoundError as exc:
    missing = exc.name or "dependency"
    print(
        f"Forge is missing Python package '{missing}'.\n"
        "Install dependencies with: pip3 install -r requirements.txt",
        file=sys.stderr,
    )
    sys.exit(1)


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


def load_yaml(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or default


def write_yaml(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=True)


def load_config() -> dict[str, Any]:
    return load_yaml(CONFIG_PATH, {})


def load_favorites() -> set[str]:
    if not FAVORITES_PATH.exists():
        return set()
    with FAVORITES_PATH.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return set(data if isinstance(data, list) else data.get("favorites", []))


def save_favorites(favorites: set[str]) -> None:
    FAVORITES_PATH.write_text(
        json.dumps(sorted(favorites), indent=2) + "\n",
        encoding="utf-8",
    )


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS command_usage (
                command_key TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                group_name TEXT NOT NULL,
                cmd TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                last_run_at TEXT
            )
            """
        )
        db.commit()


def record_usage(command: ForgeCommand) -> None:
    global _usage_cache
    _usage_cache = None
    init_db()
    with sqlite3.connect(DB_PATH) as db:
        db.execute(
            """
            INSERT INTO command_usage(command_key, name, group_name, cmd, count, last_run_at)
            VALUES (?, ?, ?, ?, 1, datetime('now'))
            ON CONFLICT(command_key) DO UPDATE SET
                count = count + 1,
                last_run_at = datetime('now'),
                cmd = excluded.cmd
            """,
            (command.key, command.name, command.group, command.cmd),
        )
        db.commit()


_usage_cache: dict[str, int] | None = None

def usage_counts() -> dict[str, int]:
    global _usage_cache
    if _usage_cache is not None:
        return _usage_cache
    if not DB_PATH.exists():
        _usage_cache = {}
        return _usage_cache
    try:
        with sqlite3.connect(DB_PATH) as db:
            _usage_cache = {
                row[0]: row[1]
                for row in db.execute("SELECT command_key, count FROM command_usage")
            }
    except sqlite3.OperationalError:
        _usage_cache = {}
    return _usage_cache


def recent_keys(limit: int = 20) -> list[str]:
    if not DB_PATH.exists():
        return []
    with sqlite3.connect(DB_PATH) as db:
        rows = db.execute(
            """
            SELECT command_key FROM command_usage
            WHERE last_run_at IS NOT NULL
            ORDER BY last_run_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [row[0] for row in rows]


def load_commands() -> list[ForgeCommand]:
    favorites = load_favorites()
    commands: list[ForgeCommand] = []
    for path in sorted(COMMANDS_DIR.glob("*.yaml")):
        data = load_yaml(path, {})
        group = data.get("group", path.stem.title())
        icon = data.get("icon", "")
        for item in data.get("commands", []):
            if not item.get("name") or not item.get("cmd"):
                continue
            command = ForgeCommand(
                name=str(item["name"]),
                cmd=str(item["cmd"]),
                group=str(item.get("group", group)),
                icon=str(item.get("icon", icon)),
                source_file=path,
                description=str(item.get("description", "")),
                tags=list(item.get("tags", []) or []),
                dangerous=bool(item.get("dangerous", False)),
                favorite=bool(item.get("favorite", False)),
                aliases=list(item.get("aliases", []) or []),
            )
            command.favorite = command.favorite or command.key in favorites
            commands.append(command)
    counts = usage_counts()
    commands.sort(key=lambda command: (-counts.get(command.key, 0), command.group, command.name))
    return commands


def status_line() -> str:
    parts: list[str] = []
    aws = os.environ.get("AWS_PROFILE")
    if aws:
        parts.append(f"AWS: {aws}")
    branch = current_git_branch()
    if branch:
        parts.append(f"Git: {branch}")
    docker_running = running_docker_count()
    if docker_running is not None:
        parts.append(f"Docker: {docker_running} running")
    parts.append(f"Shell: {Path(os.environ.get('SHELL', 'shell')).name}")
    return "  ·  ".join(parts)


def current_git_branch() -> str | None:
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return None
    branch = result.stdout.strip()
    return branch or None


def running_docker_count() -> int | None:
    if not shutil.which("docker"):
        return None
    result = subprocess.run(
        ["docker", "ps", "-q"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        return None
    return len([line for line in result.stdout.splitlines() if line.strip()])


def print_header() -> None:
    config = load_config()
    if config.get("show_status_bar", True):
        subtitle = status_line()
    else:
        subtitle = "Developer Command Operating System"
    console.print(
        Panel(
            Text(f"FORGE  -  Developer Command Operating System\n{subtitle}", justify="center"),
            border_style="cyan",
            box=box.ROUNDED,
        )
    )


def preview(command: ForgeCommand) -> None:
    tags = ", ".join(command.tags or []) or "none"
    body = (
        f"[bold]{command.label}[/bold]\n"
        f"{command.description or 'No description'}\n\n"
        f"[cyan]{command.cmd}[/cyan]\n\n"
        f"Tags: {tags}"
    )
    if command.dangerous:
        body += "\n[bold red]Dangerous command: confirmation required[/bold red]"
    if command.favorite:
        body += "\n[yellow]Favorite[/yellow]"
    console.print(Panel(body, title="Preview", border_style="magenta", box=box.ROUNDED))


def variables_for(command_text: str) -> list[str]:
    seen: list[str] = []
    for match in PLACEHOLDER_RE.finditer(command_text):
        name = match.group(1).strip()
        if name not in seen:
            seen.append(name)
    return seen


def interpolate(command: ForgeCommand) -> str | None:
    command_text = command.cmd
    for name in variables_for(command_text):
        answer = questionary.text(f"Enter {name}:").ask()
        if answer is None:
            return None
        command_text = re.sub(r"{{\s*" + re.escape(name) + r"\s*}}", answer, command_text)
    return command_text


def confirm_danger(command_text: str) -> bool:
    console.print(
        Panel(
            f"[bold red]DANGEROUS COMMAND[/bold red]\n\n{command_text}\n\nThis may modify or delete data.",
            border_style="red",
            box=box.DOUBLE,
        )
    )
    return bool(questionary.confirm("Run this command?", default=False).ask())


def shell_path() -> str:
    configured = load_config().get("shell")
    if configured and shutil.which(configured):
        return shutil.which(configured) or configured
    return os.environ.get("SHELL") or "/bin/bash"


def run_shell(command_text: str) -> int:
    start = time.time()
    console.print(Panel(f"[cyan]{command_text}[/cyan]", title="Running", border_style="green"))
    shell = shell_path()
    status = subprocess.call([shell, "-lc", command_text])
    elapsed = time.time() - start
    if elapsed >= 0.5:
        console.print(f"[dim]Done in {elapsed:.1f}s[/dim]")
    return status


def copy_command(command_text: str) -> bool:
    system = platform.system().lower()
    helpers: list[list[str]]
    if system == "darwin":
        helpers = [["pbcopy"]]
    else:
        helpers = [["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]]
    for helper in helpers:
        if shutil.which(helper[0]):
            subprocess.run(helper, input=command_text, text=True, check=False)
            return True
    return False


def execute_command(command: ForgeCommand, *, dry_run: bool = False, copy_only: bool = False) -> int:
    command_text = interpolate(command)
    if command_text is None:
        return 130
    if dry_run:
        console.print(command_text)
        return 0
    if copy_only:
        if copy_command(command_text):
            console.print("[green]Copied command to clipboard.[/green]")
            return 0
        console.print("[yellow]No clipboard helper found. Command:[/yellow]")
        console.print(command_text)
        return 1
    if command.dangerous and not confirm_danger(command_text):
        console.print("[yellow]Cancelled.[/yellow]")
        return 130
    status = run_shell(command_text)
    if status == 0:
        record_usage(command)
    return status


def grouped(commands: list[ForgeCommand]) -> dict[str, list[ForgeCommand]]:
    groups: dict[str, list[ForgeCommand]] = {}
    for command in commands:
        groups.setdefault(command.group, []).append(command)
    return groups


def group_menu(commands: list[ForgeCommand], title: str = "Select a command group") -> int:
    while True:
        selected = group_picker(commands, title)
        if selected in (None, "__quit__"):
            return 0
        if selected == "__search__":
            status = search_home(commands, "Search All Commands")
            if status != GO_BACK:
                return status
            continue
        if selected == "__favorites__":
            favs = [c for c in commands if c.favorite]
            if not favs:
                show_empty_state("Favorites")
                questionary.press_any_key_to_continue().ask()
                continue
            status = command_picker(favs, "Favorites")
            if status != GO_BACK:
                return status
            continue
        if selected == "__recents__":
            by_key = {command.key: command for command in commands}
            recents = [by_key[key] for key in recent_keys() if key in by_key]
            if not recents:
                show_empty_state("Recents")
                questionary.press_any_key_to_continue().ask()
                continue
            status = command_picker(recents, "Recents")
            if status != GO_BACK:
                return status
            continue
        groups = grouped(commands)
        status = command_picker(groups[selected], selected)
        if status != GO_BACK:
            return status


def search_home(commands: list[ForgeCommand], title: str = "Commands") -> int:
    while True:
        console.clear()
        selected = search_picker(commands, title)
        if selected is None:
            return GO_BACK
        if isinstance(selected, str) and selected.startswith("__group__:"):
            group_name = selected.removeprefix("__group__:")
            status = command_picker(grouped(load_commands()).get(group_name, []), group_name)
            if status != GO_BACK:
                return status
            continue
        if selected == "__favorites__":
            favs = [c for c in load_commands() if c.favorite]
            if not favs:
                show_empty_state("Favorites")
                questionary.press_any_key_to_continue().ask()
                continue
            status = search_home(favs, "Favorites")
            if status != GO_BACK:
                return status
            continue
        if selected == "__recents__":
            all_commands = load_commands()
            by_key = {command.key: command for command in all_commands}
            recents = [by_key[key] for key in recent_keys() if key in by_key]
            if not recents:
                show_empty_state("Recents")
                questionary.press_any_key_to_continue().ask()
                continue
            status = search_home(recents, "Recents")
            if status != GO_BACK:
                return status
            continue
        if selected == "__quit__":
            return 0
        if selected == "__add__":
            add_command(argparse.Namespace(from_history=False, name=None, cmd=None, group=None, description=None, tags="", dangerous=False))
            if title in ("Commands", "Search All Commands"):
                commands = load_commands()
            continue
        if selected == "__edit__":
            edit_group(None)
            if title in ("Commands", "Search All Commands"):
                commands = load_commands()
            continue
        if isinstance(selected, tuple):
            action, cmd = selected
            if action == "__edit_cmd__":
                edit_group(cmd.group)
                if title in ("Commands", "Search All Commands"):
                    commands = load_commands()
                continue
            if action == "__delete_cmd__":
                delete_command(cmd)
                if title in ("Commands", "Search All Commands"):
                    commands = load_commands()
                continue
            if action == "__toggle_fav__":
                toggle_favorite(cmd)
                continue
            if action == "__copy_cmd__":
                execute_command(cmd, copy_only=True)
                continue

            if action == "__cd__":
                cmd_buffer = Path.home() / ".forge" / ".forge_cmd_buffer"
                if cmd_buffer.parent.exists():
                    cmd_buffer.write_text(f"cd '{cmd}'\n", encoding="utf-8")
                return 0
            if action in ("__workflows__", "__profile__"):
                console.print(f"[yellow]{action.strip('_')} not implemented yet.[/yellow]")
                time.sleep(1)
                continue
        if isinstance(selected, ForgeCommand):
            status = command_picker([selected], "Run command")
            if status == GO_BACK:
                continue
            return status


def command_menu(commands: list[ForgeCommand], title: str) -> int:
    return command_picker(commands, title)



def is_dir_jump_mode(q: str) -> bool:
    return any(q.startswith(prefix) for prefix in ["/", "~/", "./", "../", ".."])

def search_picker(commands: list[ForgeCommand], title: str) -> ForgeCommand | str | tuple | None:
    query = ""
    selected_index = 0
    start_index = 0
    max_results = 25
    colors = get_theme_colors()
    style = build_style(colors)
    counts = usage_counts()
    current_peek_path: Path | None = None

    nav_items: list[tuple[str, str, str]] = [
        ("★ Favorites", "__favorites__"),
        ("⏱ Recents", "__recents__"),
        ("✕ Quit", "__quit__"),
    ]

    def group_items() -> list[tuple[str, str, str]]:
        grps = grouped(commands)
        return [
            (
                f"{items[0].icon} {name}  ({len(items)} commands)",
                f"__group__:{name}",
                "group",
            )
            for name, items in sorted(grps.items(), key=lambda x: -len(x[1]))
        ]

    def visible_items() -> list[ForgeCommand | tuple[str, str, str]]:
        if is_dir_jump_mode(query):
            if current_peek_path:
                target_dir = current_peek_path
                filter_text = ""
            else:
                raw_path = os.path.expanduser(query)
                if raw_path == "..":
                    raw_path = "../"
                
                if query.endswith("/") or raw_path.endswith("/"):
                    target_dir = Path(raw_path)
                    filter_text = ""
                else:
                    p = Path(raw_path)
                    if p.is_dir():
                        target_dir = p
                        filter_text = ""
                    else:
                        target_dir = p.parent
                        filter_text = p.name

            try:
                if not target_dir.exists() or not target_dir.is_dir():
                    return []
            except Exception:
                return []

            try:
                items = list(target_dir.iterdir())
            except PermissionError:
                return [("🚫 Permission Denied", "__error__", "error")]
            except Exception:
                return []
            
            if not query.endswith("."):
                items = [i for i in items if not i.name.startswith(".")]
            
            if filter_text:
                filter_lower = filter_text.lower()
                items = [i for i in items if filter_lower in i.name.lower()]
                
            items.sort(key=lambda x: (not x.is_dir(), x.name.lower()))
            
            res = []
            for idx, i in enumerate(items):
                if idx >= 500:
                    res.append(("... (Too many files to display)", "__error__", "error"))
                    break
                icon = "📁" if i.is_dir() else "📄"
                res.append((f"{icon} {i.name}", str(i), "dir" if i.is_dir() else "file"))
            return res

        if query.strip():
            command_results = ranked_commands(commands, query)[:max_results]
            return [*command_results, *nav_items]
        return [*group_items(), *nav_items]

    def clamp_index() -> None:
        nonlocal selected_index
        its = visible_items()
        selected_index = max(0, min(selected_index, len(its) - 1)) if its else 0

    def item_label(item: ForgeCommand | tuple[str, str, str]) -> str:
        if isinstance(item, ForgeCommand):
            return command_item_label(item, counts, show_badge=True)
        return item[0]

    def total_matches() -> int:
        if query.strip():
            return len(ranked_commands(commands, query))
        return 0

    def render():
        nonlocal start_index
        clamp_index()
        its = visible_items()
        cols = shutil.get_terminal_size((100, 30)).columns - 2
        box_w = max(72, min(110, cols))
        lines = shutil.get_terminal_size((100, 30)).lines

        top_lines = 5
        bottom_lines = 5
        max_visible = max(3, lines - top_lines - bottom_lines - 2)

        if selected_index < start_index:
            start_index = selected_index
        elif selected_index >= start_index + max_visible:
            start_index = selected_index - max_visible + 1

        if start_index >= len(its):
            start_index = 0
        start_index = max(0, start_index)

        visible_its = its[start_index : start_index + max_visible]

        tokens: list[tuple[str, str]] = [
            ("class:title", f" FORGE — {title}\n"),
            ("class:border", "┌" + "─" * (box_w - 2) + "┐\n"),
        ]

        search_w = box_w - 7
        search_display = short_text(query, search_w) if query else "Type to search commands..."
        search_fill = " " * (search_w - len(search_display))
        tokens.append(("class:border", "│"))
        tokens.append(("class:search", f" 🔍 {search_display}{search_fill} "))
        tokens.append(("class:border", "│\n"))
        tokens.append(("class:border", "└" + "─" * (box_w - 2) + "┘\n"))

        is_dir_jump = is_dir_jump_mode(query)
        if is_dir_jump or query.strip():
            total = len(its) if is_dir_jump else total_matches()
            shown = len(its) if is_dir_jump else min(total, max_results)
            if total == 0:
                if is_dir_jump:
                    tokens.append(("class:muted", f"\n  No files found in directory\n"))
                else:
                    tokens.append(("class:muted", f"\n  No commands match \"{query}\"\n"))
                    tokens.append(("class:help", "  Try a different search term\n"))
            else:
                if is_dir_jump:
                    tokens.append(("class:help", f"\n  {shown} items in directory\n"))
                else:
                    tokens.append(("class:help", f"\n  {shown} of {total} results\n"))
                
                for idx, item in enumerate(visible_its):
                    if isinstance(item, tuple) and item[1].startswith("__") and item[1] != "__error__":
                        continue
                    actual_idx = start_index + idx
                    ptr = "▸ " if actual_idx == selected_index else "  "
                    sty = "class:selected" if actual_idx == selected_index else "class:item"
                    tokens.append((sty, f"  {ptr}{item_label(item)}\n"))
                
                if not is_dir_jump and total > max_results:
                    tokens.append(("class:muted", f"  ... and {total - max_results} more\n"))
        else:
            if not its:
                tokens.append(("class:muted", "\n  No command groups found\n"))
                tokens.append(("class:help", '  Add commands with: commands add\n'))
            else:
                tokens.append(("", "\n"))
                for idx, item in enumerate(visible_its):
                    actual_idx = start_index + idx
                    ptr = "▸ " if actual_idx == selected_index else "  "
                    sty = "class:selected" if actual_idx == selected_index else "class:item"
                    tokens.append((sty, f"  {ptr}{item_label(item)}\n"))

        tokens.append(("class:border", "\n┌" + "─" * (box_w - 2) + "┐\n"))
        tokens.append(("class:border", "│"))
        shortcuts = "↵ Select   / Type to search   Esc Clear/Back   ^Q Quit"
        pad = box_w - 4 - len(shortcuts)
        tokens.append(("class:help", f" {shortcuts}{' ' * pad} "))
        tokens.append(("class:border", "│\n"))
        tokens.append(("class:border", "└" + "─" * (box_w - 2) + "┘\n"))
        return tokens

    kb = KeyBindings()

    @kb.add(Keys.Down, eager=True)
    def _down(event):
        nonlocal selected_index
        its = visible_items()
        if its:
            selected_index = (selected_index + 1) % len(its)

    @kb.add(Keys.Up, eager=True)
    def _up(event):
        nonlocal selected_index
        its = visible_items()
        if its:
            selected_index = (selected_index - 1) % len(its)

    @kb.add(Keys.Backspace, eager=True)
    def _backspace(event):
        nonlocal query, selected_index, current_peek_path, start_index
        if is_dir_jump_mode(query) and current_peek_path:
            current_peek_path = current_peek_path.parent
            selected_index = 0
            start_index = 0
            return
        query = query[:-1]
        current_peek_path = None
        selected_index = 0
        start_index = 0

    @kb.add(Keys.ControlU, eager=True)
    def _clear(event):
        nonlocal query, selected_index, current_peek_path, start_index
        query = ""
        current_peek_path = None
        selected_index = 0
        start_index = 0

    @kb.add(Keys.Escape, eager=True)
    def _escape(event):
        nonlocal query, selected_index, current_peek_path, start_index
        if query:
            query = ""
            current_peek_path = None
            selected_index = 0
            start_index = 0
            return
        event.app.exit(result=None)

    @kb.add(Keys.ControlQ, eager=True)
    def _quit(event):
        event.app.exit(result="__quit__")

    @kb.add(Keys.ControlA, eager=True)
    def _add_shortcut(event):
        event.app.exit(result="__add__")

    @kb.add(Keys.ControlE, eager=True)
    def _edit_shortcut(event):
        its = visible_items()
        if not its:
            event.app.exit(result="__edit__")
            return
        selected = its[selected_index]
        if isinstance(selected, ForgeCommand):
            event.app.exit(result=("__edit_cmd__", selected))
        else:
            event.app.exit(result="__edit__")

    @kb.add(Keys.ControlD, eager=True)
    def _del_shortcut(event):
        its = visible_items()
        if its:
            selected = its[selected_index]
            if isinstance(selected, ForgeCommand):
                event.app.exit(result=("__delete_cmd__", selected))

    @kb.add(Keys.ControlT, eager=True)
    def _fav_toggle_shortcut(event):
        its = visible_items()
        if its:
            selected = its[selected_index]
            if isinstance(selected, ForgeCommand):
                event.app.exit(result=("__toggle_fav__", selected))

    @kb.add(Keys.ControlF, eager=True)
    def _favs_shortcut(event):
        event.app.exit(result="__favorites__")

    @kb.add(Keys.ControlR, eager=True)
    def _recs_shortcut(event):
        event.app.exit(result="__recents__")

    @kb.add(Keys.ControlC, eager=True)
    def _copy_shortcut(event):
        its = visible_items()
        if its:
            selected = its[selected_index]
            if isinstance(selected, ForgeCommand):
                event.app.exit(result=("__copy_cmd__", selected))

    @kb.add(Keys.ControlW, eager=True)
    def _workflows_shortcut(event):
        event.app.exit(result=("__workflows__", None))

    @kb.add(Keys.ControlP, eager=True)
    def _profile_shortcut(event):
        event.app.exit(result=("__profile__", None))

    @kb.add(Keys.ControlM, eager=True)
    def _enter(event):
        its = visible_items()
        if not its:
            return
        selected = its[selected_index]
        if is_dir_jump_mode(query):
            if isinstance(selected, tuple) and selected[1] == "__error__":
                return
            if isinstance(selected, tuple):
                path = selected[1]
                if len(selected) > 2 and selected[2] == "file":
                    path = str(Path(path).parent)
                event.app.exit(result=("__cd__", path))
            return

        if isinstance(selected, tuple):
            event.app.exit(result=selected[1])
        else:
            event.app.exit(result=selected)

    @kb.add(Keys.Any)
    def _type(event):
        nonlocal query, selected_index, current_peek_path, start_index
        char = event.data
        if char and char.isprintable():
            query += char
            current_peek_path = None
            selected_index = 0
            start_index = 0

    @kb.add(Keys.Tab, eager=True)
    def _tab(event):
        nonlocal current_peek_path, selected_index, start_index
        if is_dir_jump_mode(query):
            its = visible_items()
            if its and selected_index < len(its):
                item = its[selected_index]
                if isinstance(item, tuple) and len(item) == 3 and item[2] == "dir":
                    current_peek_path = Path(item[1])
                    selected_index = 0
                    start_index = 0

    @kb.add(Keys.Right, eager=True)
    def _right(event):
        nonlocal current_peek_path, selected_index, start_index
        if is_dir_jump_mode(query):
            its = visible_items()
            if its and selected_index < len(its):
                item = its[selected_index]
                if isinstance(item, tuple) and len(item) == 3 and item[2] == "dir":
                    current_peek_path = Path(item[1])
                    selected_index = 0
                    start_index = 0

    @kb.add(Keys.Left, eager=True)
    def _left(event):
        nonlocal current_peek_path, selected_index, start_index
        if is_dir_jump_mode(query) and current_peek_path:
            current_peek_path = current_peek_path.parent
            selected_index = 0
            start_index = 0

    app = Application(
        layout=Layout(HSplit([Window(FormattedTextControl(render), always_hide_cursor=False)])),
        key_bindings=kb,
        style=style,
        full_screen=True,
    )
    return app.run()


def ranked_commands(commands: list[ForgeCommand], query: str) -> list[ForgeCommand]:
    normalized = " ".join(query.lower().split())
    if not normalized:
        return commands

    scored: list[tuple[int, str, ForgeCommand]] = []
    for command in commands:
        cmd = command.cmd.lower()
        name = command.name.lower()
        description = command.description.lower()
        group = command.group.lower()
        tags = " ".join(command.tags or []).lower()
        haystack = f"{cmd} {name} {description} {group} {tags}"
        if cmd.startswith(normalized):
            score = 1000
        elif name.startswith(normalized):
            score = 900
        elif any(part.startswith(normalized) for part in cmd.split()):
            score = 850
        elif normalized in cmd:
            score = 800
        elif normalized in haystack:
            score = 700
        else:
            score = fuzz.WRatio(normalized, haystack)
        if score >= 45:
            scored.append((int(score), command.cmd, command))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [command for _, _, command in scored]


def select_prompt(title: str, choices: list[questionary.Choice], searchable: bool = False):
    question = questionary.select(
        title,
        choices=choices,
        use_shortcuts=len(choices) <= 36 and not searchable,
        use_search_filter=searchable,
        use_jk_keys=not searchable,
        instruction=(
            "(Type to filter, Enter to select, Esc to go back)"
            if searchable
            else "(Use arrow keys, Enter to select, Esc to go back)"
        ),
    )

    @question.application.key_bindings.add(Keys.Escape, eager=True)
    def _(event):
        event.app.exit(result=None)

    return question


def short_text(value: str, limit: int) -> str:
    value = " ".join(value.split())
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)].rstrip() + "..."


def get_theme_colors() -> dict:
    theme = load_config().get("theme", "default")
    base = {
        "title": "bold #00d7ff",
        "border": "#00d7ff",
        "search_bg": "bg:#005f5f",
        "search_fg": "bold #ffffff",
        "selected": "reverse",
        "item": "",
        "nav": "#b0b0b0",
        "muted": "#666666",
        "badge": "#ffd700",
        "favorite": "#ffd700",
        "danger": "#ff4444",
        "success": "#00ff00",
        "preview_border": "#ff6b6b",
        "preview_body": "",
        "help": "#888888",
        "groups_header": "",
    }
    if theme == "minimal":
        base.update({"border": "#555555", "title": "bold", "search_bg": "", "search_fg": "", "selected": "bold", "badge": "#888888", "favorite": "#aaaaaa", "preview_border": "#888888"})
    elif theme == "compact":
        base.update({"help": "#666666", "muted": "#555555"})
    return base


def build_style(colors: dict) -> Style:
    return Style.from_dict({
        "title": colors["title"],
        "border": colors["border"],
        "search": f"{colors['search_fg']} {colors['search_bg']}",
        "search.focused": f"{colors['search_fg']} {colors['search_bg']}",
        "selected": colors["selected"],
        "item": colors["item"],
        "nav": colors["nav"],
        "muted": colors["muted"],
        "badge": colors["badge"],
        "favorite": colors["favorite"],
        "danger": colors["danger"],
        "success": colors["success"],
        "preview_border": colors["preview_border"],
        "preview_body": colors["preview_body"],
        "help": colors["help"],
        "groups_header": colors["groups_header"],
    })


def command_item_label(command: ForgeCommand, counts: dict[str, int] | None = None, show_badge: bool = True) -> str:
    fav = "★ " if command.favorite else ""
    cnt = (counts or {}).get(command.key, 0)
    badge = f" [{cnt}x]" if show_badge and cnt > 0 else ""
    desc = short_text(command.description, 50)
    cmd_text = short_text(command.cmd, 60)
    if desc:
        return f"{fav}{cmd_text} | {desc}{badge}"
    return f"{fav}{cmd_text}{badge}"


def format_preview_tokens(command: ForgeCommand, counts: dict[str, int] | None = None) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    tokens.append(("class:preview_body", f"  {command.cmd}\n"))
    if command.description:
        tokens.append(("class:muted", f"  {command.description}\n"))
    tags = ", ".join(command.tags or []) or "none"
    tokens.append(("class:muted", f"  Tags: {tags}\n"))
    cnt = (counts or {}).get(command.key, 0)
    if cnt > 0:
        tokens.append(("class:badge", f"  Used {cnt} times\n"))
    if command.favorite:
        tokens.append(("class:favorite", "  ★ Favorite\n"))
    if command.dangerous:
        tokens.append(("class:danger", "  ⚠ Dangerous\n"))
    return tokens


def show_empty_state(title: str) -> None:
    console.print(Panel(f"[yellow]Nothing here yet.[/yellow]\n\n[dim]Add commands with: commands add[/dim]", title=title, border_style="yellow"))


def show_action_overlay(command: ForgeCommand) -> str | None:
    preview(command)
    action = select_prompt(
        "Action",
        choices=[
            questionary.Choice("▶ Run", "run"),
            questionary.Choice("📋 Copy", "copy"),
            questionary.Choice("★ Toggle favorite", "favorite"),
            questionary.Choice("← Back", "back"),
            questionary.Choice("Quit", "quit"),
        ],
    ).ask()
    return action


def command_picker(commands: list[ForgeCommand], title: str) -> int:
    if not commands:
        show_empty_state(title)
        questionary.press_any_key_to_continue().ask()
        return GO_BACK

    query = ""
    selected_index = 0
    start_index = 0
    colors = get_theme_colors()
    style = build_style(colors)
    counts = usage_counts()

    def filtered() -> list[ForgeCommand]:
        if query.strip():
            return ranked_commands(commands, query)[:50]
        return commands

    def clamp_index() -> None:
        nonlocal selected_index
        items = filtered()
        if not items:
            selected_index = 0
        else:
            selected_index = max(0, min(selected_index, len(items) - 1))

    def render():
        nonlocal start_index
        clamp_index()
        items = filtered()
        cols = shutil.get_terminal_size((100, 30)).columns - 2
        box_w = max(72, min(110, cols))
        lines = shutil.get_terminal_size((100, 30)).lines

        top_lines = 5
        bottom_lines = 2
        preview_lines = 0
        if items:
            selected_cmd = items[selected_index] if selected_index < len(items) else items[0]
            preview_lines = 3 + len(format_preview_tokens(selected_cmd, counts))

        max_visible = max(3, lines - top_lines - bottom_lines - preview_lines - 2)

        if selected_index < start_index:
            start_index = selected_index
        elif selected_index >= start_index + max_visible:
            start_index = selected_index - max_visible + 1

        if start_index >= len(items):
            start_index = 0
        start_index = max(0, start_index)

        visible_items = items[start_index : start_index + max_visible]

        tokens: list[tuple[str, str]] = [
            ("class:title", f" FORGE — {title}\n"),
            ("class:border", "┌" + "─" * (box_w - 2) + "┐\n"),
        ]

        search_w = box_w - 7
        search_display = short_text(query, search_w) if query else "Type to filter..."
        search_fill = " " * (search_w - len(search_display))
        tokens.append(("class:border", "│"))
        tokens.append(("class:search", f" 🔍 {search_display}{search_fill} "))
        tokens.append(("class:border", "│\n"))
        tokens.append(("class:border", "└" + "─" * (box_w - 2) + "┘\n"))

        if not items:
            tokens.append(("class:muted", "  No matching commands\n\n"))
        else:
            tokens.append(("", "\n"))
            for idx, cmd in enumerate(visible_items):
                actual_idx = start_index + idx
                ptr = "▸ " if actual_idx == selected_index else "  "
                sty = "class:selected" if actual_idx == selected_index else "class:item"
                label = command_item_label(cmd, counts, show_badge=True)
                line = short_text(f"{ptr}{label}", box_w - 2)
                tokens.append((sty, f"  {line}\n"))

        if items:
            selected_cmd = items[selected_index] if selected_index < len(items) else items[0]
            tokens.append(("", "\n"))
            tokens.append(("class:preview_border", "  ┌─ Preview " + "─" * (box_w - 15) + "┐\n"))
            preview_tokens = format_preview_tokens(selected_cmd, counts)
            for pt in preview_tokens:
                content = pt[1].rstrip()
                if len(content) > box_w - 4:
                    content = short_text(content, box_w - 4)
                padding_len = max(0, box_w - 4 - len(content))
                tokens.append((pt[0], f"  │{content}{' ' * padding_len}│\n"))
            tokens.append(("class:preview_border", "  └" + "─" * (box_w - 4) + "┘\n"))

        tokens.append(("\n", ""))
        tokens.append(("class:help", f"  {'↵ Run':<16}{'Tab: Actions':<16}{'↑↓ Navigate':<16}{'Esc: Back':<16}\n"))

        return tokens

    kb = KeyBindings()

    @kb.add(Keys.Down, eager=True)
    def _down(event):
        nonlocal selected_index
        its = filtered()
        if its:
            selected_index = (selected_index + 1) % len(its)

    @kb.add(Keys.Up, eager=True)
    def _up(event):
        nonlocal selected_index
        its = filtered()
        if its:
            selected_index = (selected_index - 1) % len(its)

    @kb.add(Keys.Backspace, eager=True)
    def _backspace(event):
        nonlocal query, selected_index, start_index
        query = query[:-1]
        selected_index = 0
        start_index = 0

    @kb.add(Keys.ControlU, eager=True)
    def _clear(event):
        nonlocal query, selected_index, start_index
        query = ""
        selected_index = 0
        start_index = 0

    @kb.add(Keys.Escape, eager=True)
    def _escape(event):
        nonlocal query, selected_index, start_index
        if query:
            query = ""
            selected_index = 0
            start_index = 0
            return
        event.app.exit(result=GO_BACK)

    @kb.add(Keys.ControlQ, eager=True)
    def _quit(event):
        event.app.exit(result=0)

    @kb.add(Keys.ControlA, eager=True)
    def _add_shortcut(event):
        event.app.exit(result=("__add__", None))

    @kb.add(Keys.ControlE, eager=True)
    def _edit_shortcut(event):
        its = filtered()
        if not its:
            event.app.exit(result=("__edit__", None))
            return
        cmd = its[selected_index] if selected_index < len(its) else its[0]
        event.app.exit(result=("__edit_cmd__", cmd))

    @kb.add(Keys.ControlD, eager=True)
    def _del_shortcut(event):
        its = filtered()
        if its:
            cmd = its[selected_index] if selected_index < len(its) else its[0]
            event.app.exit(result=("__delete_cmd__", cmd))

    @kb.add(Keys.ControlT, eager=True)
    def _fav_toggle_shortcut(event):
        its = filtered()
        if its:
            cmd = its[selected_index] if selected_index < len(its) else its[0]
            event.app.exit(result=("__toggle_fav__", cmd))

    @kb.add(Keys.ControlF, eager=True)
    def _favs_shortcut(event):
        event.app.exit(result=("__favorites__", None))

    @kb.add(Keys.ControlR, eager=True)
    def _recs_shortcut(event):
        event.app.exit(result=("__recents__", None))

    @kb.add(Keys.ControlC, eager=True)
    def _copy_shortcut(event):
        its = filtered()
        if its:
            cmd = its[selected_index] if selected_index < len(its) else its[0]
            event.app.exit(result=("__copy_cmd__", cmd))

    @kb.add(Keys.ControlW, eager=True)
    def _workflows_shortcut(event):
        event.app.exit(result=("__workflows__", None))

    @kb.add(Keys.ControlP, eager=True)
    def _profile_shortcut(event):
        event.app.exit(result=("__profile__", None))

    @kb.add(Keys.ControlM, eager=True)
    def _enter(event):
        its = filtered()
        if not its:
            return
        cmd = its[selected_index] if selected_index < len(its) else its[0]
        event.app.exit(result=("run", cmd))

    @kb.add(Keys.Tab, eager=True)
    def _tab(event):
        its = filtered()
        if not its:
            return
        cmd = its[selected_index] if selected_index < len(its) else its[0]
        event.app.exit(result=("action", cmd))

    @kb.add(Keys.Any)
    def _type(event):
        nonlocal query, selected_index, start_index
        char = event.data
        if char and char.isprintable():
            query += char
            selected_index = 0
            start_index = 0

    app = Application(
        layout=Layout(HSplit([Window(FormattedTextControl(render), always_hide_cursor=False)])),
        key_bindings=kb,
        style=style,
        full_screen=True,
    )
    result = app.run()

    if result is None or result == 0:
        return GO_BACK if result is None else 0
    if result == GO_BACK:
        return GO_BACK

    action_type, cmd = result
    if action_type == "__add__":
        add_command(argparse.Namespace(from_history=False, name=None, cmd=None, group=None, description=None, tags="", dangerous=False))
        return GO_BACK
    if action_type == "__edit__":
        edit_group(None)
        return GO_BACK
    if action_type == "__edit_cmd__":
        edit_group(cmd.group)
        return GO_BACK
    if action_type == "__delete_cmd__":
        delete_command(cmd)
        return GO_BACK
    if action_type == "__toggle_fav__":
        toggle_favorite(cmd)
        return GO_BACK
    if action_type == "__copy_cmd__":
        execute_command(cmd, copy_only=True)
        return GO_BACK
    if action_type in ("__favorites__", "__recents__", "__workflows__", "__profile__"):
        if action_type in ("__workflows__", "__profile__"):
            console.print(f"[yellow]{action_type.strip('_')} not implemented yet.[/yellow]")
            time.sleep(1)
        return GO_BACK

    if action_type == "run":
        status = execute_command(cmd)
        if status != GO_BACK:
            return status
        return GO_BACK
    if action_type == "action":
        action = show_action_overlay(cmd)
        if action == "run":
            return execute_command(cmd)
        if action == "copy":
            execute_command(cmd, copy_only=True)
            return GO_BACK
        if action == "favorite":
            toggle_favorite(cmd)
            cmd.favorite = not cmd.favorite
            return GO_BACK
        return GO_BACK
    return GO_BACK


def group_picker(commands: list[ForgeCommand], title: str = "Select a command group") -> int:
    colors = get_theme_colors()
    style = build_style(colors)
    selected_index = 0
    start_index = 0
    groups = list(grouped(commands).items())
    groups.sort(key=lambda x: -len(x[1]))

    nav_items: list[tuple[str, str]] = [
        ("║  🔍 /  Search all commands", "__search__"),
        ("║  ★ F  Favorites", "__favorites__"),
        ("║  ⏱ R  Recents", "__recents__"),
        ("║  ✕ Q  Quit", "__quit__"),
    ]

    def visible():
        return [*groups, *nav_items]

    def clamp_index():
        nonlocal selected_index
        its = visible()
        selected_index = max(0, min(selected_index, len(its) - 1))

    def render():
        nonlocal start_index
        clamp_index()
        its = visible()
        cols = shutil.get_terminal_size((100, 30)).columns - 2
        box_w = max(72, min(110, cols))
        lines = shutil.get_terminal_size((100, 30)).lines

        top_lines = 4
        bottom_lines = 2
        max_visible = max(3, lines - top_lines - bottom_lines - 2)

        if selected_index < start_index:
            start_index = selected_index
        elif selected_index >= start_index + max_visible:
            start_index = selected_index - max_visible + 1

        if start_index >= len(its):
            start_index = 0
        start_index = max(0, start_index)

        visible_its = its[start_index : start_index + max_visible]

        tokens: list[tuple[str, str]] = [
            ("class:title", f" FORGE — {title}\n"),
            ("class:border", "┌" + "─" * (box_w - 2) + "┐\n"),
            ("class:help", " │  Select a group or action\n".center(box_w - 2).rstrip().ljust(box_w - 2) + "│\n"),
            ("class:border", "╞" + "═" * (box_w - 2) + "╡\n"),
        ]

        for idx, item in enumerate(visible_its):
            actual_idx = start_index + idx
            ptr = "▸ " if actual_idx == selected_index else "  "
            sty = "class:selected" if actual_idx == selected_index else ("class:item" if isinstance(item, tuple) is False else "class:nav")
            if isinstance(item, tuple) and len(item) == 2 and isinstance(item[1], list):
                name, items_in_group = item
                icon = items_in_group[0].icon if items_in_group else ""
                label = f"{icon} {name}  ({len(items_in_group)} commands)"
                line = short_text(f"{ptr}{label}", box_w - 4)
                tokens.append((sty, f"  {line}\n"))
            else:
                label = item[0]
                line = short_text(f"{ptr}{label}", box_w - 4)
                tokens.append((sty, f"  {line}\n"))

        tokens.append(("class:border", "└" + "─" * (box_w - 2) + "┘\n"))
        tokens.append(("class:help", f"  {'↑↓ Navigate':<20}{'↵ Select':<20}{'Esc: Back':<20}\n"))
        return tokens

    kb = KeyBindings()

    @kb.add(Keys.Down, eager=True)
    def _down(event):
        nonlocal selected_index
        its = visible()
        if its:
            selected_index = (selected_index + 1) % len(its)

    @kb.add(Keys.Up, eager=True)
    def _up(event):
        nonlocal selected_index
        its = visible()
        if its:
            selected_index = (selected_index - 1) % len(its)

    @kb.add(Keys.Escape, eager=True)
    def _escape(event):
        event.app.exit(result=None)

    @kb.add(Keys.ControlQ, eager=True)
    @kb.add(Keys.ControlC, eager=True)
    def _quit(event):
        event.app.exit(result="__quit__")

    @kb.add(Keys.ControlM, eager=True)
    def _enter(event):
        its = visible()
        if not its:
            return
        selected = its[selected_index]
        if isinstance(selected, tuple):
            event.app.exit(result=selected[0])
        else:
            event.app.exit(result=selected[1])

    @kb.add("/", eager=True)
    def _search_shortcut(event):
        event.app.exit(result="__search__")

    @kb.add("f", eager=True)
    @kb.add("F", eager=True)
    def _fav_shortcut(event):
        event.app.exit(result="__favorites__")

    @kb.add("r", eager=True)
    @kb.add("R", eager=True)
    def _rec_shortcut(event):
        event.app.exit(result="__recents__")

    @kb.add("q", eager=True)
    @kb.add("Q", eager=True)
    def _quit_shortcut(event):
        event.app.exit(result="__quit__")

    app = Application(
        layout=Layout(HSplit([Window(FormattedTextControl(render), always_hide_cursor=False)])),
        key_bindings=kb,
        style=style,
        full_screen=True,
    )
    return app.run()


def search_menu(commands: list[ForgeCommand], query: str | None = None) -> int:
    if query is None:
        return live_command_filter(commands, "Search All Commands")
    if not query:
        return 0
    matches = process.extract(
        query,
        {command.key: command.haystack for command in commands},
        scorer=fuzz.WRatio,
        limit=20,
    )
    by_key = {command.key: command for command in commands}
    results = [by_key[key] for _, score, key in matches if score >= 30]
    if not results:
        console.print("[yellow]No matching commands.[/yellow]")
        return 1
    status = command_menu(results, f"Search: {query}")
    return 0 if status == GO_BACK else status


def live_command_filter(commands: list[ForgeCommand], title: str) -> int:
    return search_home(commands, title)


def toggle_favorite(command: ForgeCommand) -> None:
    favorites = load_favorites()
    if command.key in favorites:
        favorites.remove(command.key)
        console.print(f"[yellow]Removed favorite:[/yellow] {command.name}")
    else:
        favorites.add(command.key)
        console.print(f"[green]Added favorite:[/green] {command.name}")
    save_favorites(favorites)


def find_command(commands: list[ForgeCommand], *, name: str | None = None, cmd: str | None = None) -> ForgeCommand | None:
    if cmd:
        for command in commands:
            if command.cmd == cmd:
                return command
    if name:
        lowered = name.lower()
        for command in commands:
            if command.name.lower() == lowered or lowered in [alias.lower() for alias in command.aliases or []]:
                return command
        scored = process.extractOne(name, {command.key: command.haystack for command in commands}, scorer=fuzz.WRatio)
        if scored:
            _, score, key = scored
            if score >= 70:
                return {command.key: command for command in commands}[key]
    return None


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


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "custom"


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


def edit_group(group: str | None) -> int:
    editor = os.environ.get("EDITOR") or str(load_config().get("editor", "vim")).replace("${EDITOR:-", "").rstrip("}")
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


def delete_command(command: ForgeCommand) -> None:
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


def setup(verbose: bool = True) -> int:
    COMMANDS_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        write_yaml(
            CONFIG_PATH,
            {
                "version": "1.0",
                "shell": Path(os.environ.get("SHELL", "zsh")).name or "zsh",
                "theme": "default",
                "alias": "commands",
                "show_status_bar": True,
                "context_detection": True,
                "history_limit": 100,
                "editor": os.environ.get("EDITOR", "vim"),
            },
        )
    if not FAVORITES_PATH.exists():
        save_favorites(set())
    init_db()
    if verbose:
        console.print(f"[green]Forge setup complete in {APP_DIR}[/green]")
    return 0


def list_groups() -> int:
    groups_data = grouped(load_commands())
    counts = usage_counts()
    table = Table(title="Forge Command Groups", box=box.ROUNDED, border_style="cyan")
    table.add_column("Group", style="bold")
    table.add_column("Commands", justify="right", style="cyan")
    table.add_column("Total Runs", justify="right", style="yellow")
    table.add_column("Most Used", style="green")
    for name, items in sorted(groups_data.items(), key=lambda x: -len(x[1])):
        total_runs = sum(counts.get(c.key, 0) for c in items)
        most_used = max(items, key=lambda c: counts.get(c.key, 0))
        most_used_name = short_text(most_used.name, 30) if counts.get(most_used.key, 0) > 0 else "-"
        table.add_row(f"{items[0].icon} {name}", str(len(items)), str(total_runs) if total_runs > 0 else "0", most_used_name)
    console.print(table)
    return 0


def detect_terminal() -> str | None:
    program = os.environ.get("TERM_PROGRAM", "")
    term = os.environ.get("TERM", "")
    if "gnome" in (program or "").lower() or "gnome" in term.lower():
        return "GNOME Terminal"
    if program == "Apple_Terminal":
        return "macOS Terminal.app"
    if program == "iTerm.app":
        return "iTerm2"
    if program == "kitty":
        return "Kitty"
    if program == "WezTerm":
        return "WezTerm"
    if program in ("alacritty", "Alacritty") or term == "alacritty":
        return "Alacritty"
    if "konsole" in term.lower() or "konsole" in (program or "").lower():
        return "Konsole"
    if "xterm" in term:
        return "xterm-compatible"
    return None


def install_shell_ctrl_g() -> bool:
    shell = Path(os.environ.get("SHELL", "zsh")).name
    if shell not in ("zsh", "bash"):
        console.print(f"  [yellow]Unsupported shell: {shell}[/yellow]")
        return False

    rc_file = Path.home() / (".zshrc" if shell == "zsh" else ".bashrc")
    if shell == "zsh":
        keybind_line = r'bindkey -s "^G" "commands\n"'
        comment = "# Forge: Ctrl+G launches commands"
    else:
        keybind_line = r'bind "\C-g": "commands\n"'
        comment = "# Forge: Ctrl+G launches commands"

    content = rc_file.read_text() if rc_file.exists() else ""
    if keybind_line in content:
        return True

    with rc_file.open("a") as f:
        f.write(f"\n{comment}\n{keybind_line}\n")
    console.print(f"  [green]✓ Added Ctrl+G → commands to {rc_file}[/green]")
    console.print("  [dim]  Run: source {}[/dim]".format(rc_file.name))
    return True


def print_manual_terminal_app() -> None:
    console.print("""  [bold]macOS Terminal.app — Manual setup:[/bold]
    [dim]1. Open Terminal → Settings → Profiles → [your profile] → Keyboard[/dim]
    [dim]2. Click [+] to add a keybinding:[/dim]
    [dim]   Key: C   Modifiers: ⇧⌃   Action: Send text[/dim]
    [dim]   Value: commands\\r[/dim]
    [dim]3. Click OK[/dim]""")


def print_manual_iterm2() -> None:
    console.print("""  [bold]iTerm2 — Manual setup:[/bold]
    [dim]1. Open iTerm2 → Settings → Keys → Key Bindings[/dim]
    [dim]2. Click [+] to add:[/dim]
    [dim]   Keyboard Shortcut: ^⇧C   Action: Send Text[/dim]
    [dim]   Value: commands\\n[/dim]
    [dim]3. Click OK[/dim]""")


def print_manual_gnome() -> None:
    console.print("""  [bold]GNOME Terminal — Manual setup:[/bold]
    [dim]1. Open GNOME Terminal → Preferences → [your profile] → Shortcuts[/dim]
    [dim]2. Disable 'Copy' shortcut if bound to Ctrl+Shift+C[/dim]
    [dim]3. Or use OS-level shortcut:[/dim]
    [dim]   Settings → Keyboard → View and Customize Shortcuts → Custom Shortcuts[/dim]
    [dim]   Add shortcut: Name=Forge  Command=gnome-terminal -- commands  Shortcut=^⇧C[/dim]""")


def install_terminal_ctrl_shift_c() -> bool | None:
    terminal = detect_terminal()
    if not terminal:
        console.print("  [yellow]⚠ Could not detect terminal emulator[/yellow]")
        print_manual_gnome()
        return None

    console.print(f"  Detected: [cyan]{terminal}[/cyan]")
    system = platform.system()

    if terminal == "macOS Terminal.app" and system == "Darwin":
        result = subprocess.run(
            ["osascript", "-e", """
                tell application "Terminal"
                    set profileName to name of current settings of selected tab of window 1
                    set didFind to false
                    tell application "System Events" to tell process "Terminal"
                        try
                            click menu item "Settings…" of menu "Terminal" of menu bar 1
                            delay 0.3
                            click button "Profiles" of toolbar 1 of window 1
                            delay 0.2
                            click button "Keyboard" of toolbar 1 of window 1
                            delay 0.2
                            click button "+" of group 1 of group 2 of window 1
                            delay 0.2
                            keystroke "C"
                            key code 56 using {command down, shift down}
                            delay 0.1
                            keystroke tab
                            delay 0.1
                            keystroke tab
                            delay 0.1
                            keystroke "commands"
                            delay 0.1
                            keystroke tab
                            delay 0.1
                            keystroke "commands\\r"
                            delay 0.1
                            key code 36
                        end try
                    end tell
                end tell
            """],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            console.print("  [green]✓ Ctrl+Shift+C → commands configured in Terminal.app[/green]")
            return True
        print_manual_terminal_app()
        return None

    if terminal == "iTerm2" and system == "Darwin":
        console.print("  [yellow]⚠ iTerm2 automation requires the Python API.[/yellow]")
        print_manual_iterm2()
        return None

    if terminal == "GNOME Terminal" and system == "Linux":
        try:
            gnome_path = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom-forge/"

            subprocess.run(["gsettings", "set",
                f"org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{gnome_path}",
                "name", "Open Forge"], check=False, capture_output=True)
            subprocess.run(["gsettings", "set",
                f"org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{gnome_path}",
                "command", "gnome-terminal -- commands"], check=False, capture_output=True)
            subprocess.run(["gsettings", "set",
                f"org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{gnome_path}",
                "binding", "<Control><Shift>C"], check=False, capture_output=True)

            result = subprocess.run(["gsettings", "get",
                "org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings"],
                capture_output=True, text=True, check=False)
            current = result.stdout.strip()
            if gnome_path not in current:
                if current == "@as []" or not current:
                    new_list = f"['{gnome_path}']"
                else:
                    items = current.strip()
                    if items.startswith("@as "):
                        items = items[4:]
                    items = items.strip("[]")
                    paths = [p.strip().strip("'\"") for p in items.split(",") if p.strip()]
                    if gnome_path not in paths:
                        paths.append(gnome_path)
                    new_list = "[" + ", ".join(f"'{p}'" for p in paths) + "]"
                subprocess.run(["gsettings", "set",
                    "org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings",
                    new_list], check=False, capture_output=True)

            console.print("  [green]✓ Ctrl+Shift+C → launch Forge via GNOME shortcut[/green]")
            return True
        except FileNotFoundError:
            print_manual_gnome()
            return None

    console.print(f"  [yellow]⚠ Automatic setup not available for {terminal}[/yellow]")
    if system == "Darwin":
        print_manual_terminal_app()
        print_manual_iterm2()
    else:
        print_manual_gnome()
    return None


def setup_keybind() -> int:
    console.print(Panel.fit("⚡ Forge Keyboard Shortcut Setup", border_style="cyan"))

    console.print("\n[bold]Step 1: Shell shortcut (Ctrl+G) — works in any terminal[/bold]")
    install_shell_ctrl_g()

    console.print("\n[bold]Step 2: Terminal shortcut (Ctrl+Shift+C) — opens Forge instantly[/bold]")
    console.print("  [dim](Note: This may override your terminal's Copy shortcut.)[/dim]")
    install_terminal_ctrl_shift_c()

    console.print("\n[green]Done![/green] Restart your terminal or source your shell rc file to apply.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Forge - Developer Command Operating System")
    parser.add_argument("--version", action="store_true", help="Print Forge version")
    parser.add_argument("--setup", action="store_true", help="Initialize Forge storage")
    parser.add_argument("--group", help="Open a command group")
    sub = parser.add_subparsers(dest="command")

    run_parser = sub.add_parser("run", help="Run a command by name or command text")
    run_parser.add_argument("name", nargs="?", help="Command name or alias")
    run_parser.add_argument("--cmd", help="Exact command text")
    run_parser.add_argument("--dry-run", action="store_true", help="Print the resolved command without running")
    run_parser.add_argument("--copy", action="store_true", help="Copy the command without running")

    search_parser = sub.add_parser("search", help="Search commands")
    search_parser.add_argument("query", nargs="?", help="Search query")

    add_parser = sub.add_parser("add", help="Add a command")
    add_parser.add_argument("--from-history", action="store_true", help="Import from shell history")
    add_parser.add_argument("--name")
    add_parser.add_argument("--cmd")
    add_parser.add_argument("--group")
    add_parser.add_argument("--description")
    add_parser.add_argument("--tags", default="")
    add_parser.add_argument("--dangerous", action="store_true")

    edit_parser = sub.add_parser("edit", help="Edit command YAML")
    edit_parser.add_argument("group", nargs="?")

    sub.add_parser("groups", help="List command groups")
    sub.add_parser("recents", help="Open recent commands")
    sub.add_parser("favorites", help="Open favorite commands")
    sub.add_parser("keybind", help="Set up keyboard shortcut to launch Forge")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        console.print(f"Forge {VERSION}")
        return 0
    if args.setup:
        return setup(verbose=True)

    setup(verbose=False)
    commands = load_commands()
    if args.group:
        selected = [command for command in commands if args.group.lower() in command.group.lower()]
        status = command_menu(selected, args.group)
        return 0 if status == GO_BACK else status
    if args.command == "groups":
        return list_groups()
    if args.command == "search":
        return search_menu(commands, args.query)
    if args.command == "run":
        command = find_command(commands, name=args.name, cmd=args.cmd)
        if not command and args.cmd:
            command = ForgeCommand(name=args.cmd, cmd=args.cmd, group="Ad hoc")
        if not command:
            console.print("[red]Command not found.[/red]")
            return 1
        return execute_command(command, dry_run=args.dry_run, copy_only=args.copy)
    if args.command == "add":
        return add_command(args)
    if args.command == "edit":
        return edit_group(args.group)
    if args.command == "recents":
        by_key = {command.key: command for command in commands}
        status = command_menu([by_key[key] for key in recent_keys() if key in by_key], "Recents")
        return 0 if status == GO_BACK else status
    if args.command == "favorites":
        status = command_menu([command for command in commands if command.favorite], "Favorites")
        return 0 if status == GO_BACK else status
    if args.command == "keybind":
        return setup_keybind()
    status = search_home(commands)
    return 0 if status == GO_BACK else status


if __name__ == "__main__":
    raise SystemExit(main())
