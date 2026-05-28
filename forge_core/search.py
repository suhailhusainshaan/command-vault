from rapidfuzz import fuzz
from .models import ForgeCommand

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
