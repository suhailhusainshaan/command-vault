#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${COMMAND_VAULT_REPO_URL:-https://github.com/suhailhusainshaan/terminal-helper.git}"
INSTALL_DIR="${COMMAND_VAULT_HOME:-$HOME/.command-vault}"

log() {
  printf '\033[1;36m%s\033[0m\n' "$1"
}

fail() {
  printf '\033[1;31m%s\033[0m\n' "$1" >&2
  exit 1
}

detect_shell() {
  local shell_name
  shell_name="$(basename "${SHELL:-}")"
  if [ "$shell_name" = "zsh" ] || [ "$shell_name" = "bash" ]; then
    printf '%s\n' "$shell_name"
    return
  fi
  if command -v ps >/dev/null 2>&1; then
    shell_name="$(ps -p "${PPID:-$$}" -o comm= 2>/dev/null | xargs basename 2>/dev/null || true)"
    if [ "$shell_name" = "zsh" ] || [ "$shell_name" = "bash" ]; then
      printf '%s\n' "$shell_name"
      return
    fi
  fi
  printf 'bash\n'
}

check_python() {
  command -v python3 >/dev/null 2>&1 || fail "Python 3.9+ is required. On macOS run: xcode-select --install"
  python3 - <<'PY'
import sys
if sys.version_info < (3, 9):
    raise SystemExit("Python 3.9+ is required")
PY
}

install_files() {
  local script_dir
  
  # FIX 1: Safely determine if this script is actually running from a local file directory
  if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || true)"
  else
    script_dir=""
  fi

  # Only use local files if we are certain we are running a local file copy and forge.py exists next to it
  if [ -n "$script_dir" ] && [ -f "$script_dir/command-vault.py" ]; then
    if [ "$script_dir" = "$INSTALL_DIR" ]; then
      return
    fi

    mkdir -p "$INSTALL_DIR"
    if command -v rsync >/dev/null 2>&1; then
      rsync -a --exclude='.git' "$script_dir/" "$INSTALL_DIR/"
    else
      cp -R "$script_dir/." "$INSTALL_DIR/"
    fi
    return
  fi

  # Otherwise, treat it as a clean remote network installation
  command -v git >/dev/null 2>&1 || fail "git is required to clone Command Vault"
  if [ -d "$INSTALL_DIR/.git" ]; then
    # FIX 2: Ensure git pull runs completely independently of whatever directory the user is currently standing in
    git -C "$INSTALL_DIR" pull --ff-only
  else
    rm -rf "$INSTALL_DIR"
    git clone "$REPO_URL" "$INSTALL_DIR"
  fi
}

install_dependencies() {
  python3 -m venv "$INSTALL_DIR/.venv"
  "$INSTALL_DIR/.venv/bin/python" -m pip install --upgrade pip
  "$INSTALL_DIR/.venv/bin/python" -m pip install -r "$INSTALL_DIR/requirements.txt"
}

configure_shell() {
  local shell_name="$1"
  local rc_file
  if [ "$shell_name" = "zsh" ] || [ "$shell_name" = "sh" ]; then
    rc_file="$HOME/.zshrc"
  else
    rc_file="$HOME/.bashrc"
  fi

  touch "$rc_file"
  local function_def
  function_def=$(cat << 'EOF'
command_vault_cli() {
    local cmd_file="$HOME/.command-vault/.command_vault_cmd_buffer"
    rm -f "$cmd_file"

    "$HOME/.command-vault/.venv/bin/python" "$HOME/.command-vault/command-vault.py" "$@"
    local exit_code=$?

    if [ -f "$cmd_file" ]; then
        local next_cmd=$(cat "$cmd_file")
        rm -f "$cmd_file"
        if [ -n "$next_cmd" ]; then
            eval "$next_cmd"
        fi
    fi
    return $exit_code
}
alias vault="command_vault_cli"
alias cv="vault"
alias command-vault="vault"
EOF
)

  if ! grep -F 'command_vault_cli()' "$rc_file" >/dev/null 2>&1; then
    # FIX 3: Cross-platform sed compatibility (macOS vs Linux)
    if sed --version >/dev/null 2>&1; then
      # GNU sed (Linux)
      sed -i '/alias forge=.*\/forge.py/d' "$rc_file" || true
      sed -i '/alias commands=.*\/forge.py/d' "$rc_file" || true
      sed -i '/forge_cli()/,/}/d' "$rc_file" || true
      sed -i "/alias f='forge'/d" "$rc_file" || true
      sed -i "/alias f='commands'/d" "$rc_file" || true
    else
      # BSD sed (macOS)
      sed -i '' '/alias forge=.*\/forge.py/d' "$rc_file" || true
      sed -i '' '/alias commands=.*\/forge.py/d' "$rc_file" || true
      sed -i '' '/forge_cli()/,/}/d' "$rc_file" || true
      sed -i '' "/alias f='forge'/d" "$rc_file" || true
      sed -i '' "/alias f='commands'/d" "$rc_file" || true
    fi
    
    {
      printf '\n# Command Vault - Developer Command Operating System\n'
      printf "%s\n" "$function_def"
      printf "alias f='vault'\n"
    } >> "$rc_file"
  fi

  # FIX 4: Prevent interactive shell environments from leaking custom prompt hooks/errors during setup
  if command -v "$shell_name" >/dev/null 2>&1; then
    # Run in an isolated directory to avoid local repo hook side-effects
    (cd "$HOME" && "$shell_name" -c "source \"$rc_file\"" >/dev/null 2>&1 || true)
  fi
  printf '%s\n' "$rc_file"
}

main() {
  log "Installing Command Vault..."
  check_python
  install_files
  chmod +x "$INSTALL_DIR/command-vault.py"
  install_dependencies

  local shell_name rc_file
  shell_name="$(detect_shell)"
  rc_file="$(configure_shell "$shell_name")"

  "$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/command-vault.py" --setup
  log "Command Vault installed in $INSTALL_DIR"
  log "Shell detected: $shell_name ($rc_file sourced)"
  log "Run: vault"

  log "Configuring Command Vault keyboard shortcuts..."
  "$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/command-vault.py" keybind
  log "Keyboard shortcuts configured: Ctrl+Shift+C or Ctrl+G"
}

main "$@"