import argparse
import os
import sys
import time
import questionary
from pathlib import Path
from rapidfuzz import fuzz, process
from rich import box
from rich.panel import Panel
from rich.table import Table

from .models import (
    console,
    CommandVaultCommand,
    VERSION,
    APP_DIR,
    CONFIG_PATH,
    FAVORITES_PATH,
    PLACEHOLDER_RE,
    GO_BACK,
)
from .db import (
    load_config,
    load_favorites,
    save_favorites,
    init_db,
    record_usage,
    usage_counts,
    recent_keys,
    load_commands,
    write_yaml,
)
from .system import run_shell, copy_command, setup_keybind
from .ui import (
    print_header,
    preview,
    confirm_danger,
    select_prompt,
    short_text,
    show_empty_state,
    show_action_overlay,
    search_picker,
    command_picker as ui_command_picker,
    group_picker,
    grouped,
)
from .commands_mgmt import add_command, edit_group, delete_command

def interpolate(command: CommandVaultCommand) -> str | None:
    command_text = command.cmd
    # Find variables inside {{ }}
    seen: list[str] = []
    for match in PLACEHOLDER_RE.finditer(command_text):
        name = match.group(1).strip()
        if name not in seen:
            seen.append(name)
    
    for name in seen:
        answer = questionary.text(f"Enter {name}:").ask()
        if answer is None:
            return None
        import re
        command_text = re.sub(r"{{\s*" + re.escape(name) + r"\s*}}", answer, command_text)
    return command_text

def execute_command(command: CommandVaultCommand, *, dry_run: bool = False, copy_only: bool = False) -> int:
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
    from .system import append_to_shell_history
    append_to_shell_history(command_text)
    status = run_shell(command_text)
    if status == 0:
        record_usage(command)
    return status

def group_menu(commands: list[CommandVaultCommand], title: str = "Select a command group") -> int:
    while True:
        selected = group_picker(commands, title)
        if selected in (None, "__quit__"):
            return 0
        if selected == "__search__":
            status = search_home(commands, "Search All Commands")
            if status != GO_BACK:
                questionary.press_any_key_to_continue().ask()
                continue
            continue
        if selected == "__favorites__":
            favs = [c for c in commands if c.favorite]
            if not favs:
                show_empty_state("Favorites")
                questionary.press_any_key_to_continue().ask()
                continue
            status = command_picker(favs, "Favorites")
            if status != GO_BACK:
                questionary.press_any_key_to_continue().ask()
                continue
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
                questionary.press_any_key_to_continue().ask()
                continue
            continue
        if selected == "History":
            from .ui import load_history_commands
            status = command_picker(load_history_commands(limit=100), "History")
            if status != GO_BACK:
                questionary.press_any_key_to_continue().ask()
                continue
            continue
        groups = grouped(commands)
        status = command_picker(groups[selected], selected)
        if status != GO_BACK:
            questionary.press_any_key_to_continue().ask()
            continue

def search_home(commands: list[CommandVaultCommand], title: str = "Commands") -> int:
    while True:
        console.clear()
        selected = search_picker(commands, title)
        if selected is None:
            return GO_BACK
        if isinstance(selected, str) and selected.startswith("__run_raw__:"):
            raw_cmd = selected.removeprefix("__run_raw__:")
            cmd_obj = CommandVaultCommand(
                name=raw_cmd,
                cmd=raw_cmd,
                group="Ad hoc",
                icon="⚡",
                description="Ad-hoc raw command execution",
                tags=["raw"],
            )
            status = execute_command(cmd_obj)
            if status != GO_BACK:
                questionary.press_any_key_to_continue().ask()
            continue
        if isinstance(selected, str) and selected.startswith("__group__:"):
            group_name = selected.removeprefix("__group__:")
            if group_name == "History":
                from .ui import load_history_commands
                status = command_picker(load_history_commands(limit=100), "History")
            else:
                status = command_picker(grouped(load_commands()).get(group_name, []), group_name)
            if status != GO_BACK:
                questionary.press_any_key_to_continue().ask()
                continue
            continue
        if selected == "__favorites__":
            favs = [c for c in load_commands() if c.favorite]
            if not favs:
                show_empty_state("Favorites")
                questionary.press_any_key_to_continue().ask()
                continue
            status = search_home(favs, "Favorites")
            if status != GO_BACK:
                questionary.press_any_key_to_continue().ask()
                continue
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
                questionary.press_any_key_to_continue().ask()
                continue
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
                cmd_buffer = Path.home() / ".command-vault" / ".command_vault_cmd_buffer"
                if cmd_buffer.parent.exists():
                    cmd_buffer.write_text(f"cd '{cmd}'\n", encoding="utf-8")
                try:
                    os.chdir(cmd)
                    console.print(f"[green]✓ Changed directory internally to {cmd}[/green]")
                    time.sleep(0.5)
                except Exception as e:
                    console.print(f"[red]Error changing directory: {e}[/red]")
                    time.sleep(1)
                continue
            if action in ("__workflows__", "__profile__"):
                console.print(f"[yellow]{action.strip('_')} not implemented yet.[/yellow]")
                time.sleep(1)
                continue
        if isinstance(selected, CommandVaultCommand):
            status = command_picker([selected], "Run command")
            if status == GO_BACK:
                continue
            questionary.press_any_key_to_continue().ask()
            continue

def command_picker(commands: list[CommandVaultCommand], title: str) -> int:
    result = ui_command_picker(commands, title)

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

def command_menu(commands: list[CommandVaultCommand], title: str) -> int:
    return command_picker(commands, title)

def search_menu(commands: list[CommandVaultCommand], query: str | None = None) -> int:
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

def live_command_filter(commands: list[CommandVaultCommand], title: str) -> int:
    return search_home(commands, title)

def toggle_favorite(command: CommandVaultCommand) -> None:
    favorites = load_favorites()
    if command.key in favorites:
        favorites.remove(command.key)
        console.print(f"[yellow]Removed favorite:[/yellow] {command.name}")
    else:
        favorites.add(command.key)
        console.print(f"[green]Added favorite:[/green] {command.name}")
    save_favorites(favorites)

def find_command(commands: list[CommandVaultCommand], *, name: str | None = None, cmd: str | None = None) -> CommandVaultCommand | None:
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

def setup(verbose: bool = True) -> int:
    from .models import COMMANDS_DIR
    COMMANDS_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        write_yaml(
            CONFIG_PATH,
            {
                "version": "1.0",
                "shell": Path(os.environ.get("SHELL", "zsh")).name or "zsh",
                "theme": "default",
                "alias": "vault",
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
        console.print(f"[green]Command Vault setup complete in {APP_DIR}[/green]")
    return 0

def list_groups() -> int:
    groups_data = grouped(load_commands())
    counts = usage_counts()
    table = Table(title="Command Vault Command Groups", box=box.ROUNDED, border_style="cyan")
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

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Command Vault - Developer Command Operating System")
    parser.add_argument("--version", action="store_true", help="Print Command Vault version")
    parser.add_argument("--setup", action="store_true", help="Initialize Command Vault storage")
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
    sub.add_parser("keybind", help="Set up keyboard shortcut to launch Command Vault")
    return parser

def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        console.print(f"Command Vault {VERSION}")
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
            command = CommandVaultCommand(name=args.cmd, cmd=args.cmd, group="Ad hoc")
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
