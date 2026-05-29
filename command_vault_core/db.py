import json
import sqlite3
import yaml
from pathlib import Path
from typing import Any
from .models import CommandVaultCommand, CONFIG_PATH, FAVORITES_PATH, DB_PATH, COMMANDS_DIR

_usage_cache: dict[str, int] | None = None

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

def record_usage(command: CommandVaultCommand) -> None:
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

def load_commands() -> list[CommandVaultCommand]:
    favorites = load_favorites()
    commands: list[CommandVaultCommand] = []
    for path in sorted(COMMANDS_DIR.glob("*.yaml")):
        data = load_yaml(path, {})
        group = data.get("group", path.stem.title())
        icon = data.get("icon", "")
        for item in data.get("commands", []):
            if not item.get("name") or not item.get("cmd"):
                continue
            command = CommandVaultCommand(
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
