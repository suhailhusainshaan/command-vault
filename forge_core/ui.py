import os
import shutil
import questionary
from pathlib import Path
from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import Style
from rich import box
from rich.panel import Panel
from rich.text import Text
from .models import console, ForgeCommand, GO_BACK
from .db import load_config, usage_counts, recent_keys, load_commands
from .system import status_line, run_shell, copy_command
from .search import ranked_commands

def grouped(commands: list[ForgeCommand]) -> dict[str, list[ForgeCommand]]:
    groups: dict[str, list[ForgeCommand]] = {}
    for command in commands:
        groups.setdefault(command.group, []).append(command)
    return groups

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

def confirm_danger(command_text: str) -> bool:
    console.print(
        Panel(
            f"[bold red]DANGEROUS COMMAND[/bold red]\n\n{command_text}\n\nThis may modify or delete data.",
            border_style="red",
            box=box.DOUBLE,
        )
    )
    return bool(questionary.confirm("Run this command?", default=False).ask())

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
    return app.run()

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
