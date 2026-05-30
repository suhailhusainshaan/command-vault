import os
import platform
import shutil
import subprocess
import time
from pathlib import Path
from rich.panel import Panel
from .models import console, APP_DIR, CONFIG_PATH, FAVORITES_PATH
from .db import load_config, save_favorites

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

def shell_path() -> str:
    configured = load_config().get("shell")
    if configured and shutil.which(configured):
        return shutil.which(configured) or configured
    return os.environ.get("SHELL") or "/bin/bash"

def append_to_shell_history(command_text: str) -> None:
    shell_name = Path(os.environ.get("SHELL", "")).name
    candidates = []
    if shell_name == "zsh":
        candidates.append(Path.home() / ".zsh_history")
    if shell_name == "bash":
        candidates.append(Path.home() / ".bash_history")
    candidates.extend([Path.home() / ".zsh_history", Path.home() / ".bash_history"])
    
    history_path = None
    for candidate in candidates:
        if candidate.exists():
            history_path = candidate
            break
            
    if not history_path:
        return
        
    try:
        with history_path.open("a", encoding="utf-8", errors="ignore") as f:
            if history_path.name == ".zsh_history":
                f.write(f": {int(time.time())}:0;{command_text}\n")
            else:
                f.write(f"{command_text}\n")
    except Exception:
        pass

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
        keybind_line = r"""bindkey -s '^G' 'vault\n'"""
        comment = "# Command Vault: Ctrl+G launches vault"
        legacy_lines: list[str] = []
    else:
        keybind_line = r"""bind '"\C-g":"vault\n"'"""
        comment = "# Command Vault: Ctrl+G launches vault"
        legacy_lines = ['bind "\\C-g": "vault\\n"']

    content = rc_file.read_text() if rc_file.exists() else ""
    if legacy_lines:
        fixed_lines = [line for line in content.splitlines() if line.strip() not in legacy_lines]
        if fixed_lines != content.splitlines():
            rc_file.write_text("\n".join(fixed_lines) + ("\n" if fixed_lines else ""))
            content = rc_file.read_text()

    if keybind_line in content:
        return True

    with rc_file.open("a") as f:
        f.write(f"\n{comment}\n{keybind_line}\n")
    console.print(f"  [green]✓ Added Ctrl+G → vault to {rc_file}[/green]")
    console.print("  [dim]  Run: source {}[/dim]".format(rc_file.name))
    return True

def print_manual_terminal_app() -> None:
    console.print("""  [bold]macOS Terminal.app — Manual setup:[/bold]
    [dim]1. Open Terminal → Settings → Profiles → [your profile] → Keyboard[/dim]
    [dim]2. Click [+] to add a keybinding:[/dim]
    [dim]   Key: C   Modifiers: ⇧⌃   Action: Send text[/dim]
    [dim]   Value: vault\\r[/dim]
    [dim]3. Click OK[/dim]""")

def print_manual_iterm2() -> None:
    console.print("""  [bold]iTerm2 — Manual setup:[/bold]
    [dim]1. Open iTerm2 → Settings → Keys → Key Bindings[/dim]
    [dim]2. Click [+] to add:[/dim]
    [dim]   Keyboard Shortcut: ^⇧C   Action: Send Text[/dim]
    [dim]   Value: vault\\n[/dim]
    [dim]3. Click OK[/dim]""")

def print_manual_gnome() -> None:
    console.print("""  [bold]GNOME Terminal — Manual setup:[/bold]
    [dim]1. Open GNOME Terminal → Preferences → [your profile] → Shortcuts[/dim]
    [dim]2. Disable 'Copy' shortcut if bound to Ctrl+Shift+C[/dim]
    [dim]3. Or use OS-level shortcut:[/dim]
    [dim]   Settings → Keyboard → View and Customize Shortcuts → Custom Shortcuts[/dim]
    [dim]   Add shortcut: Name=Command Vault  Command=gnome-terminal -- vault  Shortcut=^⇧C[/dim]""")

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
                            keystroke "vault"
                            delay 0.1
                            keystroke tab
                            delay 0.1
                            keystroke "vault\\r"
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
            console.print("  [green]✓ Ctrl+Shift+C → vault configured in Terminal.app[/green]")
            return True
        print_manual_terminal_app()
        return None

    if terminal == "iTerm2" and system == "Darwin":
        console.print("  [yellow]⚠ iTerm2 automation requires the Python API.[/yellow]")
        print_manual_iterm2()
        return None

    if terminal == "GNOME Terminal" and system == "Linux":
        try:
            gnome_path = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom-command-vault/"

            subprocess.run(["gsettings", "set",
                f"org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{gnome_path}",
                "name", "Open Command Vault"], check=False, capture_output=True)
            subprocess.run(["gsettings", "set",
                f"org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{gnome_path}",
                "command", "gnome-terminal -- vault"], check=False, capture_output=True)
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

            console.print("  [green]✓ Ctrl+Shift+C → launch Command Vault via GNOME shortcut[/green]")
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
    console.print(Panel.fit("⚡ Command Vault Keyboard Shortcut Setup", border_style="cyan"))

    console.print("\n[bold]Step 1: Shell shortcut (Ctrl+G) — works in any terminal[/bold]")
    install_shell_ctrl_g()

    console.print("\n[bold]Step 2: Terminal shortcut (Ctrl+Shift+C) — opens Command Vault instantly[/bold]")
    console.print("  [dim](Note: This may override your terminal's Copy shortcut.)[/dim]")
    install_terminal_ctrl_shift_c()

    console.print("\n[green]Done![/green] Restart your terminal or source your shell rc file to apply.")
    return 0
