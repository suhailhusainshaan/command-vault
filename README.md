# ⚡ Forge

**The Developer Command Operating System**

A beautiful, interactive terminal tool that stores all your development commands — organized, searchable, and runnable with a single keypress. Built for engineers who work across Python, PHP, Laravel, Filament, Node.js, React, and AWS.

---

## Quick Start

```bash
curl -fsSL https://raw.githubusercontent.com/yourusername/forge/main/install.sh | bash
```

Then:

```bash
commands
```

That's it. You're in.

---

## MVP Status

This implementation covers the Weeks 1-3 roadmap from `FORGE_SPEC.md`:

- YAML command storage and parsing from `commands/*.yaml`
- Interactive group and command navigation with previews
- Command execution, variable prompts, copy-only mode, and dangerous-command confirmations
- Fuzzy search across names, descriptions, tags, groups, aliases, and command text
- Favorites, recents, frequency tracking, and `commands add --from-history`

The README sections for workflows, shell alias syncing, workspaces, import/export, and update commands describe the Week 4+ roadmap and are not part of this MVP build.

---

## Requirements

| Requirement | macOS | Ubuntu |
|---|---|---|
| Python 3.9+ | ✅ Pre-installed | ✅ Pre-installed |
| pip3 | ✅ Included | `sudo apt install python3-pip` |
| curl | ✅ Pre-installed | ✅ Pre-installed |

> No Go, no Rust, no special runtimes. Forge is designed to work on a fresh developer machine.

---

## Installation

### One-Command Install (Recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/yourusername/forge/main/install.sh | bash
```

The installer automatically:
- Verifies Python 3.9+ is available
- Clones Forge into `~/.forge`
- Creates `~/.forge/.venv` and installs Python dependencies there
- Adds the `commands` alias to your `~/.zshrc` or `~/.bashrc`
- Sources your shell config so `commands` works immediately

### Manual Install

```bash
# 1. Clone the repo
git clone https://github.com/yourusername/forge ~/.forge

# 2. Install Python dependencies in Forge's private virtualenv
python3 -m venv ~/.forge/.venv
~/.forge/.venv/bin/python -m pip install -r ~/.forge/requirements.txt

# 3. Add the alias to your shell
echo "alias commands='~/.forge/.venv/bin/python ~/.forge/forge.py'" >> ~/.zshrc
source ~/.zshrc

# 4. Initialize Forge config
commands --setup
```

### Verify Installation

```bash
commands --version
```

---

## Uninstall

```bash
rm -rf ~/.forge
# Then remove the alias line from ~/.zshrc or ~/.bashrc
```

---

## Usage

### Launch Forge

```bash
commands
```

Opens the main menu with all your command groups.

### Keyboard Navigation

| Key | Action |
|---|---|
| `↑` / `↓` | Navigate commands |
| `Enter` | Run selected command |
| `/` | Open fuzzy search |
| `Ctrl+A` | Add a new command |
| `Ctrl+E` | Edit selected command |
| `Ctrl+D` | Delete selected command |
| `Ctrl+T` | Toggle Favorite on selected command |
| `Ctrl+F` | Open Favorites view |
| `Ctrl+R` | Open Recents view |
| `Ctrl+C` | Copy command to clipboard (no run) |
| `Ctrl+W` | Open Workflows |
| `Ctrl+P` | Switch workspace profile |
| `Ctrl+Q` / `Esc` | Go back / Quit |

---

## Searching Commands

Press `/` from anywhere to open global fuzzy search.

```
  /  > laravel queue
  ────────────────────────────────────────
    PHP & Laravel  →  Start queue worker
    PHP & Laravel  →  Restart all workers
    PHP & Laravel  →  List failed jobs
    PHP & Laravel  →  Retry failed job
  ────────────────────────────────────────
  [Enter] Select   [Esc] Cancel
```

Search works across command names, descriptions, tags, and group names simultaneously.

---

## Running a Command with Variables

When you select a command that has `{{placeholders}}`, Forge prompts you for each value before running:

```
  Selected: aws sqs send-message --queue-url {{queue_url}} --message-body '{{message_body}}'
  ──────────────────────────────────────────────────────────────
  Enter queue_url: https://sqs.us-east-1.amazonaws.com/123/MyQueue
  Enter message_body: {"event": "user.created", "id": 42}
  ──────────────────────────────────────────────────────────────
  Running: aws sqs send-message --queue-url https://... --message-body '{"event":...}'
```

---

## Adding Commands

### Method 1 — Interactive CLI

Forge walks you through a form:

```bash
commands add
```

```
  Add New Command
  ───────────────
  Name:        My new command
  Command:     php artisan {{action}}
  Group:       PHP & Laravel
  Description: Run any artisan action
  Tags:        laravel, artisan
  Dangerous?:  n
```

### Method 2 — From Shell History

```bash
commands add --from-history
```

Forge scans `~/.zsh_history` (or bash history), shows you frequently run commands, and lets you import them with one keypress.

### Method 3 — Direct CLI

```bash
commands add \
  --name "Deploy to staging" \
  --cmd "kubectl apply -f k8s/staging/" \
  --group "Kubernetes" \
  --tags "kubernetes,deploy,staging" \
  --dangerous
```

### Method 4 — Edit YAML Directly

```bash
commands edit laravel
# Opens ~/.forge/commands/laravel.yaml in your $EDITOR
```

---

## Editing Commands

```bash
commands edit                   # Interactive picker
commands edit laravel           # Edit the laravel group file
```

Or press `e` on any command in the preview pane.

---

## Deleting Commands

You can delete the currently selected command by pressing `Ctrl+D`. 
Forge will prompt you for confirmation and securely remove it from the underlying YAML file.

You can also manually delete commands by editing their YAML files:

```bash
commands edit laravel
```

---

## Managing Favorites

Press `f` on any command to pin it as a Favorite.

Press `F` from the main menu to open the Favorites view — all your most important commands in one place.

Favorites are also sorted by usage frequency, so the commands you run most often rise to the top automatically over time.

---

## Workflows

Workflows run multiple commands in sequence as a single action.

### Using a Workflow

Press `w` from the main menu to see available workflows.

### Creating a Workflow

```bash
commands workflow create
```

Or add one to `~/.forge/workflows/` manually:

```yaml
# ~/.forge/workflows/laravel-dev-start.yaml
name: "🚀 Start Laravel Dev Environment"
description: "Migrate, seed, queue worker, and serve"
steps:
  - cmd: "php artisan migrate:fresh --seed"
    wait: true
    description: "Fresh database setup"
  - cmd: "php artisan queue:work &"
    description: "Start queue worker in background"
  - cmd: "npm run dev &"
    description: "Start Vite dev server"
  - cmd: "php artisan serve"
    description: "Start Laravel server"
```

---

## Aliases

Aliases are shortcuts to Forge groups, commands, or workflows — usable both inside the TUI and as shell commands.

### Defining Aliases

Edit `~/.forge/aliases.yaml`:

```yaml
aliases:
  - alias: "serve"
    target_cmd: "php artisan serve"
    description: "Start Laravel server immediately"

  - alias: "start"
    target_workflow: "Start Laravel Dev Environment"
    description: "Start full dev stack"

  - alias: "cc"
    target_cmd: "php artisan optimize:clear"
    description: "Clear all Laravel caches"
```

### Sync Aliases to Shell

After editing `aliases.yaml`, run:

```bash
commands aliases --sync
```

This writes shell aliases to your `~/.zshrc` / `~/.bashrc` so you can run them directly from the terminal without entering the Forge menu.

---

## Workspace Profiles

Switch your entire development context — environment variables, kubectl context, AWS profile, and pinned commands — in one command.

### Using a Workspace

```bash
commands workspace payments-service
```

### Creating a Workspace

```bash
commands workspace create
```

Or create a file at `~/.forge/workspaces/my-workspace.yaml`:

```yaml
name: payments-service
cwd: ~/projects/payments-service
env:
  APP_ENV: local
  DB_DATABASE: payments_db
aws_profile: payments-dev
kubectl_context: payments-staging
pinned_commands:
  - "Start queue worker"
  - "Run migrations"
  - "Get queue depth"
```

---

## Exporting & Importing Your Vault

### Export

```bash
commands export > my-forge-vault.yaml
```

Creates a portable file of your entire command library — perfect for sharing with teammates or backing up.

### Import

```bash
commands import my-forge-vault.yaml
```

Merges the imported commands into your existing vault. Existing commands are never overwritten.

```bash
# Import directly from a URL (e.g. a teammate's GitHub)
commands import https://raw.githubusercontent.com/teammate/forge-vault/main/vault.yaml
```

---

## Updating Forge

```bash
commands update
```

Pulls the latest version from GitHub and reinstalls dependencies automatically.

---

## Command Groups Included

Forge ships with pre-loaded commands for:

| Group | What's included |
|---|---|
| 🐍 **Python** | venv, pip, pytest, coverage |
| 🐘 **PHP / Laravel** | Artisan make:*, migrations, cache, queue, tinker, composer |
| 🪄 **Filament** | Install, make:resource, make:page, make:widget, optimize |
| 🟢 **Node.js** | npm init, install, run, build, audit, update |
| ⚛️ **React** | Vite scaffold, Next.js, build, test, Tailwind, packages |
| 📬 **Amazon SQS** | Create, send, receive, delete, purge, attributes, FIFO |
| 🔀 **Git** | Status, log, branch, push, stash, rebase, cherry-pick |
| 🐳 **Docker** | Compose, exec, logs, prune, build, stats |
| ⚙️ **System** | Port check, process kill, disk usage, process monitor |

All commands are fully configurable — add, edit, or delete anything.

---

## Configuration

### Global Settings

Edit `~/.forge/config.yaml`:

```yaml
version: "1.0"
shell: zsh                  # zsh | bash | fish
theme: default              # default | minimal | compact
alias: commands                # main launch command
show_status_bar: true       # live AWS/Git/Docker status line
context_detection: true     # auto-detect project type and surface relevant commands
history_limit: 100          # number of recent commands to store
editor: vim                 # editor opened by `commands edit`
```

### Themes

```bash
commands config --theme minimal    # Minimal (less color)
commands config --theme compact    # Compact (less whitespace)
commands config --theme default    # Full (default)
```

---

## File Locations

| File | Purpose |
|---|---|
| `~/.forge/config.yaml` | Global settings |
| `~/.forge/aliases.yaml` | Alias definitions |
| `~/.forge/commands/*.yaml` | Command groups (one file per group) |
| `~/.forge/workflows/*.yaml` | Multi-step workflow definitions |
| `~/.forge/workspaces/*.yaml` | Workspace profile definitions |
| `~/.forge/intelligence.db` | SQLite — usage history and frequency data |
| `~/.forge/favorites.json` | Pinned favorites |

---

## Tips & Tricks

**Jump straight to a group from shell:**
```bash
commands --group laravel
```

**Run a specific command without opening the menu:**
```bash
commands run --cmd "php artisan serve"
```

**Search from the command line:**
```bash
commands search "queue"
```

**See what Forge would run without executing:**
```bash
commands run --cmd "php artisan migrate:fresh --seed" --dry-run
```

**Open the config file:**
```bash
commands config --edit
```

---

## Troubleshooting

**`commands: command not found`**
```bash
source ~/.zshrc   # or ~/.bashrc
# If still missing:
echo "alias commands='$HOME/.forge/.venv/bin/python $HOME/.forge/forge.py'" >> ~/.zshrc && source ~/.zshrc
```

**Python version too old**
```bash
python3 --version   # Must be 3.9 or higher
# macOS: xcode-select --install
# Ubuntu: sudo apt install python3.11
```

**Missing pip packages**
```bash
~/.forge/.venv/bin/python -m pip install -r ~/.forge/requirements.txt
```

**Permission denied**
```bash
chmod +x ~/.forge/forge.py
```

**Reset Forge to defaults**
```bash
commands --reset
# WARNING: This deletes all custom commands, aliases, and history
```

---

## Contributing

1. Fork the repo
2. Add your commands to the relevant YAML file in `commands/`
3. Open a pull request

Command additions, workflow ideas, and bug reports are all welcome.

---

## License

MIT — use it, fork it, share it, build on it.

---

*Forge — because your terminal should work for you, not against you.*
