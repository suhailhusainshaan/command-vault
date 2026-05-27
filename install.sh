#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${FORGE_REPO_URL:-https://github.com/yourusername/forge.git}"
INSTALL_DIR="${FORGE_HOME:-$HOME/.forge}"

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
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
  if [ -n "$script_dir" ] && [ -f "$script_dir/forge.py" ]; then
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

  command -v git >/dev/null 2>&1 || fail "git is required to clone Forge"
  if [ -d "$INSTALL_DIR/.git" ]; then
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
  if [ "$shell_name" = "zsh" ]; then
    rc_file="$HOME/.zshrc"
  else
    rc_file="$HOME/.bashrc"
  fi

  touch "$rc_file"
  local alias_line
  alias_line="alias commands='$INSTALL_DIR/.venv/bin/python $INSTALL_DIR/forge.py'"

  if ! grep -F "$alias_line" "$rc_file" >/dev/null 2>&1; then
    sed -i.bak '/alias forge=.*\/forge.py/d' "$rc_file"
    sed -i.bak '/alias commands=.*\/forge.py/d' "$rc_file"
    sed -i.bak "/alias f='forge'/d" "$rc_file"
    sed -i.bak "/alias f='commands'/d" "$rc_file"
    {
      printf '\n# Forge - Developer Command Operating System\n'
      printf "%s\n" "$alias_line"
      printf "alias f='commands'\n"
    } >> "$rc_file"
  fi

  if command -v "$shell_name" >/dev/null 2>&1; then
    "$shell_name" -lc "source \"$rc_file\"" >/dev/null 2>&1 || true
  fi
  printf '%s\n' "$rc_file"
}

main() {
  log "Installing Forge..."
  check_python
  install_files
  chmod +x "$INSTALL_DIR/forge.py"
  install_dependencies

  local shell_name rc_file
  shell_name="$(detect_shell)"
  rc_file="$(configure_shell "$shell_name")"

  "$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/forge.py" --setup
  log "Forge installed in $INSTALL_DIR"
  log "Shell detected: $shell_name ($rc_file sourced)"
  log "Run: commands"

  log "Configuring Forge keyboard shortcuts..."
  "$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/forge.py" keybind
  log "Keyboard shortcuts configured: Ctrl+Shift+C or Ctrl+G"
}

main "$@"
