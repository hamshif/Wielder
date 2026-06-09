#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/install_apt_helpers.sh"

log() {
  printf '[install-visualizer] %s\n' "$*"
}

fail() {
  printf '[install-visualizer] ERROR: %s\n' "$*" >&2
  exit 1
}

ensure_graphviz() {
  if command -v dot >/dev/null 2>&1; then
    log "Graphviz already available: $(dot -V 2>&1)"
  else
    log "Installing Graphviz for DOT/SVG/PNG/PDF rendering."
    apt_get_safe update
    apt_get_safe install -y graphviz

    command -v dot >/dev/null 2>&1 || fail "Graphviz installation completed but dot is not on PATH."
    log "Graphviz installed: $(dot -V 2>&1)"
  fi
}

ensure_browser_open_helpers() {
  if command -v xdg-open >/dev/null 2>&1; then
    log "xdg-open already available."
    return
  fi

  log "Installing xdg-utils for opening generated HTML/SVG reports from WSL."
  apt_get_safe update
  apt_get_safe install -y xdg-utils
  command -v xdg-open >/dev/null 2>&1 || fail "xdg-utils installation completed but xdg-open is not on PATH."
}

install_vscode_extension_if_available() {
  local extension_id="$1"
  if ! command -v code >/dev/null 2>&1; then
    log "VS Code CLI is not on PATH; skipping extension ${extension_id}."
    return
  fi

  if code --list-extensions 2>/dev/null | grep -Fxq "${extension_id}"; then
    log "VS Code extension already installed: ${extension_id}"
    return
  fi

  log "Installing VS Code extension: ${extension_id}"
  code --install-extension "${extension_id}" || log "VS Code extension install failed: ${extension_id}"
}

ensure_vscode_visualizer_extensions() {
  install_vscode_extension_if_available "bierner.markdown-mermaid"
  install_vscode_extension_if_available "EFanZh.graphviz-preview"
}

ensure_graphviz
ensure_browser_open_helpers
ensure_vscode_visualizer_extensions
