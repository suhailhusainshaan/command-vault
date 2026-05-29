# ⚡ Command Vault — The Developer Command Operating System
### *One alias. Every command. Zero friction.*

> A searchable, beautiful, context-aware terminal productivity platform for engineers.
> Built by developers. For developers. The kind of tool people stop and ask about.

---

## Table of Contents

1. [Requirements & Prerequisites](#requirements--prerequisites)
2. [Product Vision](#product-vision)
3. [Architecture Decision](#architecture-decision)
4. [Core Features](#core-features)
5. [Command Library](#command-library)
6. [Alias System](#alias-system)
7. [Command Management (Add / Edit / Delete)](#command-management)
8. [Advanced Features](#advanced-features)
9. [Data Structure & Config Schema](#data-structure--config-schema)
10. [File Structure](#file-structure)
11. [Tech Stack](#tech-stack)
12. [One-Command Installation](#one-command-installation)
13. [MVP Roadmap](#mvp-roadmap)
14. [Future Vision](#future-vision)

---

## Requirements & Prerequisites

### Runtime — Use What's Already on Your Machine

> **Design Principle:** Command Vault must install and run with zero pre-installed dependencies beyond what ships with macOS or Ubuntu by default. No Go, no Rust, no special runtimes.

#### macOS
| Dependency | Pre-installed? | Version Needed | Notes |
|---|---|---|---|
| **Python 3** | ✅ Yes (macOS 12.3+) | 3.9+ | Ships with modern macOS via Xcode CLI tools |
| **pip3** | ✅ Yes | Latest | Included with Python 3 |
| **zsh / bash** | ✅ Yes | Any | Default shell on macOS |
| **curl** | ✅ Yes | Any | Used by the one-command installer |

> If Python 3 is missing: `xcode-select --install` (installs Xcode CLI tools including Python 3)

#### Ubuntu / Debian Linux
| Dependency | Pre-installed? | Version Needed | Notes |
|---|---|---|---|
| **Python 3** | ✅ Yes (Ubuntu 20.04+) | 3.9+ | Ships with Ubuntu |
| **pip3** | ⚠️ Usually yes | Latest | `sudo apt install python3-pip` if missing |
| **bash / zsh** | ✅ Yes | Any | Default shell |
| **curl** | ✅ Yes | Any | Used by installer |

#### Python Packages (Auto-installed by Command Vault installer)
| Package | Purpose |
|---|---|
| `rich` | Beautiful terminal rendering, panels, colors |
| `questionary` | Smooth interactive prompts and menus |
| `PyYAML` | YAML config file parsing |
| `rapidfuzz` | Fast fuzzy search across vault |
| `prompt_toolkit` | Advanced keyboard navigation |

> All packages install automatically via `pip3` during Command Vault setup. No manual steps needed.

#### Optional Power-Ups (Not required)
| Tool | Purpose | Install |
|---|---|---|
| `fzf` | Blazing fast external fuzzy finder | `brew install fzf` / `apt install fzf` |
| `aws-cli` | Required for AWS/SQS vault to work | `brew install awscli` |
| `php` + `composer` | Required for Laravel/PHP vault | Per project |

#### Why Not Go?
Go is an excellent language but is **not pre-installed** on macOS or Ubuntu. Requiring users to install a separate runtime defeats the "zero friction" goal. The plan is:
- **MVP in Python** — ships immediately, works on every dev machine
- **Future rewrite in Go** (BubbleTea + LipGloss) — for native binary distribution, zero runtime, elite TUI performance

This is the same path taken by tools like `httpie` (Python → Rust) and many others. Validate first, optimize later.

---

## Product Vision

You are not building a command manager.

You are building a **terminal productivity platform for engineers**.

That distinction changes everything: architecture, UX, extensibility, branding, and long-term potential.

**Command Vault** is:
- A searchable command library
- A workflow automation engine
- A context-aware development assistant
- Eventually: an AI-powered engineering console

```
╭────────────────────────────────────────────────────────────╮
│  ⚡ COMMAND VAULT  —  Developer Command Operating System           │
│  AWS: prod · K8s: staging · Git: main · Docker: running   │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  🐍 Python           8 vault                            │
│  🐘 PHP / Laravel   24 vault                            │
│  🪄 Filament         9 vault                            │
│  🟢 Node.js         12 vault                            │
│  ⚛️  React            8 vault                            │
│  📬 Amazon SQS      10 vault                            │
│  🔀 Git             14 vault                            │
│  🐳 Docker          12 vault                            │
│  ⚙️  System           8 vault                            │
│                                                            │
│  [/] Search   [a] Add   [f] Favorites   [r] Recent        │
╰────────────────────────────────────────────────────────────╯
```

---

## Architecture Decision

### Python First. Go Later.

| Phase | Stack | Why |
|---|---|---|
| **MVP** | Python 3 | Pre-installed, rapid iteration, rich ecosystem, validate UX fast |
| **v2.0** | Go + BubbleTea + LipGloss | Native binary, zero dependencies, elite TUI performance |

This is the optimal path. Build fast, validate the UX and command library, then rewrite the runtime in Go for production-grade distribution. Many successful tools follow this exact pattern.

---

## Core Features

### 1. Beautiful Interactive TUI

Not a primitive `select` menu. A full terminal UI with:
- Rounded borders and colored panels
- Group icons and command counts
- Highlighted selection, dimmed context
- Bottom status bar with all shortcuts
- Smooth keyboard navigation

### 2. Fuzzy Search Everywhere (The Killer Feature)

Press `/` from any screen. Search across:
- Command names
- Descriptions
- Tags
- Group names
- Aliases

```
> laravel queue
─────────────────────────────────────────
  Laravel  →  Start queue worker
  Laravel  →  Restart all workers
  Laravel  →  List failed jobs
─────────────────────────────────────────
```

### 3. Command Preview Pane

Every command shows a preview before execution:

```
──────────────────────────────────────────────
  php artisan queue:work --tries=3 --timeout=90
──────────────────────────────────────────────
  [Enter] Run    [e] Edit    [c] Copy    [f] Favorite
──────────────────────────────────────────────
```

### 4. Parameterized Commands (Variable Interpolation)

Commands with `{{placeholders}}` prompt you to fill values before running:

```yaml
- name: "SSH into EC2"
  cmd: "ssh ubuntu@{{ip_address}}"

- name: "SQS - Send test message"
  cmd: "aws sqs send-message --queue-url {{queue_url}} --message-body '{{message}}'"

- name: "Artisan make:model"
  cmd: "php artisan make:model {{ModelName}} -m"
```

Command Vault intercepts, prompts for each `{{variable}}`, builds the final command, then executes.

### 5. Safety Layer for Dangerous Commands

```yaml
- name: "Nuke Docker everything"
  cmd: "docker system prune -af"
  dangerous: true
```

Command Vault shows a warning panel before any `dangerous: true` command:

```
  ╔══════════════════════════════════════╗
  ║  ⚠️  DANGEROUS COMMAND               ║
  ║                                      ║
  ║  docker system prune -af             ║
  ║                                      ║
  ║  Deletes ALL unused containers,      ║
  ║  images, networks, and build cache.  ║
  ║                                      ║
  ║  [y] Confirm     [N] Cancel          ║
  ╚══════════════════════════════════════╝
```

### 6. Favorites & Recents

- `[f]` pins any command to Favorites
- Recent vault auto-surface at the top of each session
- Frequency sorting — the more you run it, the higher it floats
- Dedicated Favorites view (`[f]` key from main menu)

### 7. Multi-Step Workflows

One action — entire sequence runs:

```yaml
workflows:
  - name: "🚀 Start Laravel Dev Environment"
    description: "Migrate, seed, and serve"
    steps:
      - cmd: "php artisan migrate:fresh --seed"
        wait: true
      - cmd: "php artisan queue:work &"
      - cmd: "npm run dev &"
      - cmd: "php artisan serve"
```

### 8. Directory-Aware Context Detection

Command Vault detects your project type and surfaces relevant vault:

| Detected file | Auto-surface |
|---|---|
| `artisan` | Laravel vault group |
| `package.json` | Node / React group |
| `docker-compose.yml` | Docker group |
| `terraform` files | Infrastructure group |
| `requirements.txt` / `setup.py` | Python group |

### 9. Live Status Bar

Always visible at the top:
```
  AWS: prod  ·  Git: feature/auth  ·  Docker: 3 running  ·  PHP: 8.3
```

### 10. Copy Without Running

`[c]` in preview pane copies the full constructed command to clipboard — useful for pasting into Slack, docs, or a different terminal.

### 11. Shell History Import

`command-vault add --from-history` scans `~/.zsh_history` or `~/.bash_history`, shows frequently used vault, and lets you import with one keypress.

### 12. Tags & Filtering

```yaml
tags: [production, dangerous, deploy, laravel]
```

Filter by `#production` or `#dangerous` to scope the view.

---

## Command Library

> These are the pre-loaded vault in Command Vault. All configurable — add, edit, delete anytime.

---

### 🐍 Python

```yaml
group: Python
icon: "🐍"
vault:
  - name: "Create virtual environment"
    cmd: "python3 -m venv venv"
    description: "Create a new venv in current directory"
    tags: [python, setup]

  - name: "Activate venv (macOS/Linux)"
    cmd: "source venv/bin/activate"
    description: "Activate the virtual environment"
    tags: [python, setup]

  - name: "Install from requirements"
    cmd: "pip install -r requirements.txt"
    description: "Install all project dependencies"
    tags: [python, packages]

  - name: "Freeze requirements"
    cmd: "pip freeze > requirements.txt"
    description: "Save current packages to requirements.txt"
    tags: [python, packages]

  - name: "Run script"
    cmd: "python3 {{script_name}}.py"
    description: "Run a Python script"
    tags: [python, run]

  - name: "Run tests (pytest)"
    cmd: "pytest -v"
    description: "Run all tests with verbose output"
    tags: [python, testing]

  - name: "Run tests with coverage"
    cmd: "pytest --cov={{app_folder}} --cov-report=html"
    description: "Run tests and generate HTML coverage report"
    tags: [python, testing]

  - name: "Check outdated packages"
    cmd: "pip list --outdated"
    description: "List all packages with available updates"
    tags: [python, packages]
```

---

### 🐘 PHP / Laravel

```yaml
group: PHP & Laravel
icon: "🐘"
vault:
  # --- Server & Environment ---
  - name: "Serve application"
    cmd: "php artisan serve"
    description: "Start Laravel development server on :8000"
    tags: [laravel, server]

  - name: "Serve on custom port"
    cmd: "php artisan serve --port={{port}}"
    description: "Start server on a specific port"
    tags: [laravel, server]

  # --- Make: Generators ---
  - name: "Make controller"
    cmd: "php artisan make:controller {{ControllerName}}"
    description: "Create a new controller class"
    tags: [laravel, make]

  - name: "Make resource controller"
    cmd: "php artisan make:controller {{ControllerName}} --resource"
    description: "Create controller with full CRUD methods"
    tags: [laravel, make]

  - name: "Make model + migration"
    cmd: "php artisan make:model {{ModelName}} -m"
    description: "Create a model and its migration file"
    tags: [laravel, make, database]

  - name: "Make model + migration + controller"
    cmd: "php artisan make:model {{ModelName}} -mcr"
    description: "Create model, migration, and resource controller"
    tags: [laravel, make]

  - name: "Make migration"
    cmd: "php artisan make:migration {{migration_name}}"
    description: "Create a new migration file"
    tags: [laravel, make, database]

  - name: "Make seeder"
    cmd: "php artisan make:seeder {{SeederName}}"
    description: "Create a new database seeder"
    tags: [laravel, make, database]

  - name: "Make factory"
    cmd: "php artisan make:factory {{FactoryName}} --model={{ModelName}}"
    description: "Create a model factory"
    tags: [laravel, make, database]

  - name: "Make request"
    cmd: "php artisan make:request {{RequestName}}"
    description: "Create a form request validation class"
    tags: [laravel, make]

  - name: "Make middleware"
    cmd: "php artisan make:middleware {{MiddlewareName}}"
    description: "Create a new middleware class"
    tags: [laravel, make]

  - name: "Make job"
    cmd: "php artisan make:job {{JobName}}"
    description: "Create a new queued job class"
    tags: [laravel, make, queue]

  - name: "Make event"
    cmd: "php artisan make:event {{EventName}}"
    description: "Create a new event class"
    tags: [laravel, make]

  - name: "Make listener"
    cmd: "php artisan make:listener {{ListenerName}} --event={{EventName}}"
    description: "Create an event listener"
    tags: [laravel, make]

  - name: "Make command"
    cmd: "php artisan make:command {{CommandName}}"
    description: "Create a new Artisan command"
    tags: [laravel, make]

  # --- Database ---
  - name: "Run migrations"
    cmd: "php artisan migrate"
    description: "Run all pending database migrations"
    tags: [laravel, database, migrate]

  - name: "Fresh migrate + seed"
    cmd: "php artisan migrate:fresh --seed"
    description: "Drop all tables, re-run migrations, and seed"
    tags: [laravel, database, migrate]
    dangerous: true

  - name: "Rollback last migration"
    cmd: "php artisan migrate:rollback"
    description: "Rollback the last batch of migrations"
    tags: [laravel, database, migrate]
    dangerous: true

  - name: "Migration status"
    cmd: "php artisan migrate:status"
    description: "Show status of each migration"
    tags: [laravel, database]

  - name: "Run seeders"
    cmd: "php artisan db:seed"
    description: "Run all database seeders"
    tags: [laravel, database]

  - name: "Run specific seeder"
    cmd: "php artisan db:seed --class={{SeederName}}"
    description: "Run a specific seeder class"
    tags: [laravel, database]

  # --- Cache & Optimization ---
  - name: "Clear all caches"
    cmd: "php artisan optimize:clear"
    description: "Clear config, route, view, and app cache"
    tags: [laravel, cache]

  - name: "Cache config"
    cmd: "php artisan config:cache"
    description: "Cache configuration for faster loading"
    tags: [laravel, cache, deploy]

  - name: "Cache routes"
    cmd: "php artisan route:cache"
    description: "Cache routes for better performance"
    tags: [laravel, cache, deploy]

  - name: "Optimize for production"
    cmd: "php artisan optimize"
    description: "Cache config, routes, and views for production"
    tags: [laravel, cache, deploy]

  - name: "Clear application cache"
    cmd: "php artisan cache:clear"
    description: "Flush the application cache"
    tags: [laravel, cache]

  - name: "Clear config cache"
    cmd: "php artisan config:clear"
    description: "Remove the configuration cache"
    tags: [laravel, cache]

  # --- Routes ---
  - name: "List all routes"
    cmd: "php artisan route:list"
    description: "Display all registered application routes"
    tags: [laravel, routes]

  - name: "List routes (filtered)"
    cmd: "php artisan route:list --name={{filter}}"
    description: "Filter routes by name pattern"
    tags: [laravel, routes]

  # --- Queue ---
  - name: "Start queue worker"
    cmd: "php artisan queue:work"
    description: "Start processing queued jobs"
    tags: [laravel, queue]

  - name: "Queue worker (with options)"
    cmd: "php artisan queue:work --tries={{tries}} --timeout={{timeout}}"
    description: "Start worker with retry and timeout limits"
    tags: [laravel, queue]

  - name: "Restart queue workers"
    cmd: "php artisan queue:restart"
    description: "Signal all workers to restart after current job"
    tags: [laravel, queue]

  - name: "List failed jobs"
    cmd: "php artisan queue:failed"
    description: "List all failed queue jobs"
    tags: [laravel, queue]

  - name: "Retry failed job"
    cmd: "php artisan queue:retry {{job_id}}"
    description: "Retry a specific failed job by ID"
    tags: [laravel, queue]

  - name: "Flush all failed jobs"
    cmd: "php artisan queue:flush"
    description: "Delete all failed job records"
    tags: [laravel, queue]
    dangerous: true

  # --- Tinker & Debug ---
  - name: "Open Tinker REPL"
    cmd: "php artisan tinker"
    description: "Interactive REPL to experiment with your Laravel app"
    tags: [laravel, debug]

  # --- Maintenance ---
  - name: "Enable maintenance mode"
    cmd: "php artisan down"
    description: "Put the application in maintenance mode"
    tags: [laravel, maintenance]
    dangerous: true

  - name: "Disable maintenance mode"
    cmd: "php artisan up"
    description: "Bring the application out of maintenance mode"
    tags: [laravel, maintenance]

  # --- Composer ---
  - name: "Install dependencies"
    cmd: "composer install"
    description: "Install all PHP packages from composer.lock"
    tags: [laravel, composer]

  - name: "Update dependencies"
    cmd: "composer update"
    description: "Update all PHP packages to latest versions"
    tags: [laravel, composer]

  - name: "Require a package"
    cmd: "composer require {{vendor/package}}"
    description: "Add a new Composer package"
    tags: [laravel, composer]

  - name: "Dump autoload"
    cmd: "composer dump-autoload"
    description: "Regenerate the Composer autoload files"
    tags: [laravel, composer]
```

---

### 🪄 Filament

```yaml
group: Filament
icon: "🪄"
vault:
  - name: "Install Filament panels"
    cmd: "composer require filament/filament:\"^3.3\" -W && php artisan filament:install --panels"
    description: "Install and initialize Filament panel builder"
    tags: [filament, setup]

  - name: "Create admin user"
    cmd: "php artisan make:filament-user"
    description: "Create a new Filament admin panel user"
    tags: [filament, setup]

  - name: "Make Filament resource"
    cmd: "php artisan make:filament-resource {{ModelName}} --generate"
    description: "Create a Filament resource with auto-generated form/table"
    tags: [filament, make]

  - name: "Make Filament resource (simple)"
    cmd: "php artisan make:filament-resource {{ModelName}} --simple"
    description: "Create a modal-based (simple) Filament resource"
    tags: [filament, make]

  - name: "Make Filament page"
    cmd: "php artisan make:filament-page {{PageName}}"
    description: "Create a custom Filament admin page"
    tags: [filament, make]

  - name: "Make Filament widget"
    cmd: "php artisan make:filament-widget {{WidgetName}}"
    description: "Create a dashboard widget"
    tags: [filament, make]

  - name: "Make Filament relation manager"
    cmd: "php artisan make:filament-relation-manager {{ResourceName}} {{relationship}} {{attribute}}"
    description: "Create a relation manager for a resource"
    tags: [filament, make]

  - name: "Optimize Filament (production)"
    cmd: "php artisan filament:optimize"
    description: "Cache Filament components and icons for production"
    tags: [filament, deploy, cache]

  - name: "Clear Filament cache"
    cmd: "php artisan filament:optimize-clear"
    description: "Clear all Filament component caches"
    tags: [filament, cache]
```

---

### 🟢 Node.js

```yaml
group: Node.js
icon: "🟢"
vault:
  - name: "Initialize new project"
    cmd: "npm init -y"
    description: "Create a new package.json with defaults"
    tags: [node, setup]

  - name: "Install dependencies"
    cmd: "npm install"
    description: "Install all packages from package.json"
    tags: [node, packages]

  - name: "Install package"
    cmd: "npm install {{package_name}}"
    description: "Add a new package to the project"
    tags: [node, packages]

  - name: "Install package (dev)"
    cmd: "npm install --save-dev {{package_name}}"
    description: "Add a package as a dev dependency"
    tags: [node, packages]

  - name: "Uninstall package"
    cmd: "npm uninstall {{package_name}}"
    description: "Remove a package from the project"
    tags: [node, packages]

  - name: "Run start script"
    cmd: "npm start"
    description: "Run the start script from package.json"
    tags: [node, run]

  - name: "Run dev script"
    cmd: "npm run dev"
    description: "Run the dev script (usually with hot-reload)"
    tags: [node, run]

  - name: "Run build"
    cmd: "npm run build"
    description: "Build the project for production"
    tags: [node, build, deploy]

  - name: "Run tests"
    cmd: "npm test"
    description: "Run the test suite"
    tags: [node, testing]

  - name: "List outdated packages"
    cmd: "npm outdated"
    description: "Check which packages have newer versions"
    tags: [node, packages]

  - name: "Update all packages"
    cmd: "npm update"
    description: "Update packages to their latest allowed versions"
    tags: [node, packages]

  - name: "Audit for vulnerabilities"
    cmd: "npm audit"
    description: "Check for known security vulnerabilities"
    tags: [node, security]

  - name: "Fix audit vulnerabilities"
    cmd: "npm audit fix"
    description: "Automatically fix vulnerability issues"
    tags: [node, security]

  - name: "List globally installed packages"
    cmd: "npm list -g --depth=0"
    description: "Show all globally installed npm packages"
    tags: [node, packages]

  - name: "Clear npm cache"
    cmd: "npm cache clean --force"
    description: "Clear the npm package cache"
    tags: [node, cache]
    dangerous: true

  - name: "Run with Node directly"
    cmd: "node {{filename}}.js"
    description: "Run a JavaScript file directly with Node"
    tags: [node, run]
```

---

### ⚛️ React

```yaml
group: React
icon: "⚛️"
vault:
  - name: "Create React app (Vite)"
    cmd: "npm create vite@latest {{app_name}} -- --template react"
    description: "Scaffold a new React app using Vite (recommended 2025)"
    tags: [react, setup]

  - name: "Create React app (CRA)"
    cmd: "npx create-react-app {{app_name}}"
    description: "Scaffold using Create React App (legacy)"
    tags: [react, setup]

  - name: "Create Next.js app"
    cmd: "npx create-next-app@latest {{app_name}}"
    description: "Scaffold a new Next.js application"
    tags: [react, nextjs, setup]

  - name: "Start dev server"
    cmd: "npm run dev"
    description: "Start Vite/Next.js development server with HMR"
    tags: [react, run]

  - name: "Build for production"
    cmd: "npm run build"
    description: "Create optimized production build"
    tags: [react, build, deploy]

  - name: "Preview production build"
    cmd: "npm run preview"
    description: "Serve the production build locally for testing"
    tags: [react, build]

  - name: "Run tests (Jest)"
    cmd: "npm test -- --watchAll=false"
    description: "Run all tests once (non-watch mode)"
    tags: [react, testing]

  - name: "Install React Router"
    cmd: "npm install react-router-dom"
    description: "Add client-side routing to the app"
    tags: [react, packages]

  - name: "Install Axios"
    cmd: "npm install axios"
    description: "Add HTTP client for API requests"
    tags: [react, packages]

  - name: "Install Tailwind CSS"
    cmd: "npm install -D tailwindcss postcss autoprefixer && npx tailwindcss init -p"
    description: "Set up Tailwind CSS in a React project"
    tags: [react, packages, styling]
```

---

### 📬 Amazon SQS

```yaml
group: Amazon SQS
icon: "📬"
vault:
  - name: "List all queues"
    cmd: "aws sqs list-queues"
    description: "List all SQS queues in your AWS account"
    tags: [sqs, aws, list]

  - name: "List queues by prefix"
    cmd: "aws sqs list-queues --queue-name-prefix {{prefix}}"
    description: "Filter queues by name prefix"
    tags: [sqs, aws, list]

  - name: "Get queue URL"
    cmd: "aws sqs get-queue-url --queue-name {{queue_name}}"
    description: "Retrieve the URL of an SQS queue"
    tags: [sqs, aws]

  - name: "Create standard queue"
    cmd: "aws sqs create-queue --queue-name {{queue_name}}"
    description: "Create a new standard SQS queue"
    tags: [sqs, aws, create]

  - name: "Create FIFO queue"
    cmd: "aws sqs create-queue --queue-name {{queue_name}}.fifo --attributes FifoQueue=true,ContentBasedDeduplication=true"
    description: "Create a FIFO queue (ordered, exactly-once delivery)"
    tags: [sqs, aws, create]

  - name: "Get queue attributes"
    cmd: "aws sqs get-queue-attributes --queue-url {{queue_url}} --attribute-names All"
    description: "Get all attributes of a queue (depth, retention, etc.)"
    tags: [sqs, aws, inspect]

  - name: "Send message"
    cmd: "aws sqs send-message --queue-url {{queue_url}} --message-body '{{message_body}}'"
    description: "Send a single message to a queue"
    tags: [sqs, aws, send]

  - name: "Receive messages"
    cmd: "aws sqs receive-message --queue-url {{queue_url}} --max-number-of-messages {{count}} --wait-time-seconds 10"
    description: "Poll and receive messages (long polling)"
    tags: [sqs, aws, receive]

  - name: "Delete message"
    cmd: "aws sqs delete-message --queue-url {{queue_url}} --receipt-handle {{receipt_handle}}"
    description: "Delete a specific message by receipt handle"
    tags: [sqs, aws, delete]

  - name: "Purge queue (delete all messages)"
    cmd: "aws sqs purge-queue --queue-url {{queue_url}}"
    description: "Delete ALL messages in the queue immediately"
    tags: [sqs, aws, delete]
    dangerous: true

  - name: "Delete queue"
    cmd: "aws sqs delete-queue --queue-url {{queue_url}}"
    description: "Permanently delete an SQS queue"
    tags: [sqs, aws, delete]
    dangerous: true

  - name: "Set queue visibility timeout"
    cmd: "aws sqs set-queue-attributes --queue-url {{queue_url}} --attributes VisibilityTimeout={{seconds}}"
    description: "Update how long messages are hidden after being received"
    tags: [sqs, aws, config]

  - name: "Get queue depth (approx. message count)"
    cmd: "aws sqs get-queue-attributes --queue-url {{queue_url}} --attribute-names ApproximateNumberOfMessages"
    description: "Check how many messages are waiting in the queue"
    tags: [sqs, aws, inspect]
```

---

### 🔀 Git

```yaml
group: Git
icon: "🔀"
vault:
  - name: "Status"
    cmd: "git status"
    tags: [git]

  - name: "Pretty log (graph)"
    cmd: "git log --oneline --graph --decorate --all"
    description: "Visual branch graph in terminal"
    tags: [git, log]

  - name: "Stage all changes"
    cmd: "git add -A"
    tags: [git]

  - name: "Commit with message"
    cmd: "git commit -m '{{message}}'"
    tags: [git]

  - name: "Push current branch"
    cmd: "git push origin $(git branch --show-current)"
    tags: [git, push]

  - name: "Force push (with lease — safe)"
    cmd: "git push --force-with-lease"
    description: "Safe force push — fails if remote has changes you haven't fetched"
    tags: [git, push]

  - name: "Pull with rebase"
    cmd: "git pull --rebase"
    tags: [git, pull]

  - name: "Create and switch to new branch"
    cmd: "git checkout -b {{branch_name}}"
    tags: [git, branch]

  - name: "Undo last commit (keep changes staged)"
    cmd: "git reset --soft HEAD~1"
    tags: [git, undo]

  - name: "Stash changes"
    cmd: "git stash push -m '{{stash_message}}'"
    tags: [git, stash]

  - name: "Pop stash"
    cmd: "git stash pop"
    tags: [git, stash]

  - name: "Interactive rebase"
    cmd: "git rebase -i HEAD~{{n}}"
    description: "Interactively edit last N commits"
    tags: [git, rebase]

  - name: "Delete local merged branches"
    cmd: "git branch --merged | grep -v 'main\\|master\\|develop' | xargs git branch -d"
    description: "Clean up local branches already merged into main"
    tags: [git, branch, cleanup]

  - name: "Cherry pick commit"
    cmd: "git cherry-pick {{commit_hash}}"
    tags: [git]
```

---

### 🐳 Docker

```yaml
group: Docker
icon: "🐳"
vault:
  - name: "Compose up (rebuild)"
    cmd: "docker compose up --build"
    tags: [docker]

  - name: "Compose up (detached)"
    cmd: "docker compose up -d"
    tags: [docker]

  - name: "Compose down"
    cmd: "docker compose down"
    tags: [docker]

  - name: "Compose down (remove volumes)"
    cmd: "docker compose down -v"
    description: "Stop and remove containers AND volumes"
    tags: [docker]
    dangerous: true

  - name: "List running containers"
    cmd: "docker ps"
    tags: [docker, inspect]

  - name: "Exec into container"
    cmd: "docker exec -it {{container_name}} bash"
    description: "Open a bash shell inside a running container"
    tags: [docker, exec]

  - name: "View container logs"
    cmd: "docker logs -f {{container_name}}"
    tags: [docker, logs]

  - name: "Remove all stopped containers"
    cmd: "docker container prune -f"
    tags: [docker, cleanup]
    dangerous: true

  - name: "Remove dangling images"
    cmd: "docker image prune -f"
    tags: [docker, cleanup]

  - name: "Nuke everything"
    cmd: "docker system prune -af"
    description: "Remove ALL unused containers, images, volumes, networks"
    tags: [docker, cleanup]
    dangerous: true

  - name: "Build image"
    cmd: "docker build -t {{image_name}}:{{tag}} ."
    tags: [docker, build]

  - name: "Watch container stats"
    cmd: "docker stats"
    tags: [docker, inspect]
```

---

## Alias System

Command Vault includes a dedicated **Alias** section. An alias is a short custom command that maps to a Command Vault group, command, or workflow.

### Alias Config Format

```yaml
# ~/.command-vault/aliases.yaml

aliases:
  # Run a full workflow by short name
  - alias: "start"
    target_workflow: "Start Laravel Dev Environment"
    description: "Start full dev stack"

  # Jump directly to a group
  - alias: "lq"
    target_group: "PHP & Laravel"
    filter: "queue"
    description: "Open Laravel queue vault"

  # Run a specific command directly, skipping the menu
  - alias: "serve"
    target_cmd: "php artisan serve"
    description: "Start Laravel server immediately"

  # Run multiple vault as a quick sequence
  - alias: "cc"
    target_cmd: "php artisan optimize:clear"
    description: "Clear all Laravel caches"
```

### Shell-Level Aliases (Auto-generated)

During setup, Command Vault writes these to your `~/.zshrc` or `~/.bashrc`:

```bash
# Command Vault — auto-generated aliases
alias command-vault='python3 ~/.command-vault/command-vault.py'
alias f='command-vault'

# Optional short aliases (user-configurable in ~/.command-vault/aliases.yaml)
alias fserve='command-vault run --cmd "php artisan serve"'
alias fmigrate='command-vault run --cmd "php artisan migrate"'
alias fqueue='command-vault group "PHP & Laravel" --filter queue'
```

Users can add/remove shell-level aliases by editing `~/.command-vault/aliases.yaml` and running `command-vault aliases --sync`.

---

## Command Management

### Adding Commands

**Method 1 — Interactive TUI**
Press `[a]` from the main menu. Command Vault walks you through:
```
  Name:         Deploy to staging
  Command:      kubectl apply -f k8s/staging/
  Group:        Kubernetes
  Description:  Apply all staging manifests
  Tags:         kubernetes, deploy, staging
  Dangerous?:   n
```

**Method 2 — From shell history**
```bash
command-vault add --from-history
```
Shows recent vault from `~/.zsh_history`, select one, categorize it.

**Method 3 — Direct CLI**
```bash
command-vault add --name "Run migrations" --cmd "php artisan migrate" --group "PHP & Laravel" --tags "laravel,database"
```

**Method 4 — Edit YAML directly**
```bash
command-vault edit laravel     # Opens ~/.command-vault/vault/laravel.yaml in $EDITOR
```

---

### Editing Commands

```bash
command-vault edit              # Opens interactive group picker, then command picker
command-vault edit --group laravel --name "Run migrations"   # Edit specific command
```

Or press `[e]` on any command in the preview pane to edit it inline.

---

### Deleting Commands

```bash
command-vault delete --group laravel --name "Run migrations"   # Delete by name
command-vault delete --interactive                              # Pick from TUI
```

Or press `[d]` in the command list to delete after confirmation.

---

### Exporting & Importing

```bash
command-vault export > my-vault.yaml       # Export entire vault to portable file
command-vault import my-vault.yaml         # Import from a file (merges, no overwrites)
command-vault import https://raw.githubusercontent.com/.../vault.yaml   # Import from URL
```

---

## Advanced Features

### Command Intelligence (Killer Feature)

Command Vault tracks which vault you run and when. Over time it:
- Auto-suggests related vault after you run one
- Surfaces vault you haven't used in a while (rediscovery)
- Detects patterns and proposes creating a workflow

```
  You just ran: php artisan migrate
  ─────────────────────────────────
  Often run next:
    → php artisan db:seed
    → php artisan queue:work
```

Data stored in `~/.command-vault/intelligence.db` (SQLite). Fully local, never leaves your machine.

### Workspace Profiles

```bash
command-vault workspace payments-service
```

Loads a named profile:
```yaml
# ~/.command-vault/workspaces/payments-service.yaml
name: payments-service
cwd: ~/projects/payments-service
env:
  APP_ENV: local
  DB_DATABASE: payments_db
kubectl_context: payments-staging
aws_profile: payments-dev
pinned_commands:
  - "Start queue worker"
  - "Run migrations"
  - "Tail SQS queue depth"
```

Everything — environment, context, pinned vault — loads in one command.

### AI Command Assistant (v3.0, future)

Describe what you want in plain English:

```
> explain the sqs receive command
> generate a workflow to deploy Laravel to staging
> what does php artisan queue:work --tries do
```

Architectured into the data model from day one. Added as an LLM integration in v3.0.

---

## Data Structure & Config Schema

### Full Command Schema

```yaml
- name: string              # required — short label shown in TUI
  cmd: string               # required — shell command, may contain {{variables}}
  description: string       # optional — shown in preview pane
  group: string             # optional — overrides file-level group
  tags: [string]            # optional — for filtering and search
  dangerous: bool           # optional — triggers warning before execution (default: false)
  favorite: bool            # optional — pre-pinned to Favorites
  aliases: [string]         # optional — short names for this command
  variables:                # optional — explicit variable definitions
    - name: variable_name
      prompt: "Enter the queue URL:"
      default: ""
```

### Global Config

```yaml
# ~/.command-vault/config.yaml
version: "1.0"
shell: zsh                  # zsh | bash | fish
theme: default              # default | minimal | compact
alias: command-vault                # main launch alias
show_status_bar: true       # live AWS/K8s/Git status line
context_detection: true     # auto-detect project type
history_limit: 100          # number of recent vault to track
editor: $EDITOR             # editor for `command-vault edit`
```

---

## File Structure

```
~/.command-vault/
├── command-vault.py                 # Main application entry point
├── config.yaml              # Global settings
├── aliases.yaml             # Alias definitions
├── requirements.txt         # Python dependencies
│
├── vault/                # One YAML file per group (editable)
│   ├── python.yaml
│   ├── laravel.yaml
│   ├── filament.yaml
│   ├── node.yaml
│   ├── react.yaml
│   ├── sqs.yaml
│   ├── git.yaml
│   ├── docker.yaml
│   └── system.yaml
│
├── workflows/               # Multi-step workflow definitions
│   ├── laravel-dev-start.yaml
│   └── deploy-staging.yaml
│
├── workspaces/              # Named workspace profiles
│   └── example-workspace.yaml
│
├── intelligence.db          # SQLite — command frequency + history
└── favorites.json           # Pinned favorites list
```

---

## Tech Stack

### MVP Stack (Python)

| Layer | Technology | Reason |
|---|---|---|
| Language | **Python 3.9+** | Pre-installed on macOS/Ubuntu, zero friction |
| TUI Framework | **Textual** or **prompt_toolkit** | Full keyboard nav, rich layouts |
| Terminal Rendering | **rich** | Colors, panels, tables, markdown |
| Prompts | **questionary** | Smooth interactive variable prompts |
| Config | **PyYAML** | Human-readable, commentable, version-controllable |
| Fuzzy Search | **rapidfuzz** | Fast in-memory fuzzy matching |
| Persistence | **SQLite** (built-in) | Command history, frequency tracking |
| Shell Execution | **subprocess** (built-in) | Robust command execution |

### Future Stack (Go)

| Layer | Technology |
|---|---|
| Language | Go |
| TUI | BubbleTea |
| Styling | LipGloss |
| Storage | YAML + SQLite |
| Distribution | Single native binary (no runtime needed) |

---

## One-Command Installation

The entire setup — clone, install dependencies, generate config, add alias — happens with a single command:

```bash
curl -fsSL https://raw.githubusercontent.com/yourusername/command-vault/main/install.sh | bash
```

Or with `wget`:

```bash
wget -qO- https://raw.githubusercontent.com/yourusername/command-vault/main/install.sh | bash
```

### What the installer does (in order):

1. Checks Python 3.9+ is available (prompts to install via Xcode CLI tools if missing on Mac)
2. Clones the Command Vault repo into `~/.command-vault`
3. Runs `pip3 install -r ~/.command-vault/requirements.txt`
4. Detects current shell (`zsh` / `bash`)
5. Writes `alias command-vault='python3 ~/.command-vault/command-vault.py'` to `~/.zshrc` or `~/.bashrc`
6. Sources the shell config (`source ~/.zshrc`)
7. Runs `command-vault --setup` to initialize config files
8. Prints a success message with first steps

After install, the user only needs to type:
```bash
command-vault
```

That's it. No manual config, no PATH changes, no environment setup.

---

## MVP Roadmap

### Week 1 — Foundation
- YAML command storage and parser
- Group navigation with keyboard arrows
- Command preview pane
- Execute command on Enter

### Week 2 — Search & UX
- Fuzzy search across all groups (`/` key)
- Parameterized command prompts (`{{variable}}`)
- Copy to clipboard mode (`[c]`)
- Dangerous command safety warnings

### Week 3 — Polish & Persistence
- Beautiful TUI — colors, icons, borders, status bar
- Favorites system (`[f]` key)
- Recents and frequency sorting
- Shell history import (`command-vault add --from-history`)

### Week 4 — Power Features
- Multi-step workflows
- Directory-aware context detection
- Alias system with `aliases.yaml`
- `command-vault add` / `command-vault edit` / `command-vault delete` CLI vault

### Week 5 — Intelligence & Workspaces
- Command Intelligence (SQLite-backed usage tracking + suggestions)
- Workspace profiles (`command-vault workspace <name>`)
- Export / import vault

### Week 6+ — Future
- AI Command Assistant (LLM integration)
- Team sync via Git URL
- Cloud backup to private repo
- Go rewrite for native binary distribution
- Plugin system

---

## Future Vision

```
Level 1  →  Personal command launcher         (MVP)
Level 2  →  Team workflow platform            (v2.0)
Level 3  →  AI-powered engineering assistant  (v3.0)
Level 4  →  Developer operating system        (v4.0)
```

Most CLI tools optimize for **functionality.**
Very few optimize for **developer experience, aesthetics, discoverability, and flow state.**

That is where Command Vault becomes genuinely special.

---

*Command Vault — because your terminal should work for you, not against you.*

> Contributions, forks, and feedback welcome.
> The best version of this gets built with many minds, not one.
