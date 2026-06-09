#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${DIR}/install_apt_helpers.sh"

log() {
  printf '[install-azure-cli] %s\n' "$*"
}

fail() {
  printf '[install-azure-cli] ERROR: %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  local cmd="$1"
  command -v "$cmd" >/dev/null 2>&1 || fail "Required command not found: ${cmd}"
}

ensure_base_packages() {
  apt_get_safe update
  apt_get_safe install -y ca-certificates curl gnupg lsb-release
}

install_microsoft_repo() {
  local arch codename repo_line

  sudo install -m 0755 -d /etc/apt/keyrings
  if [[ ! -f /etc/apt/keyrings/microsoft.asc ]]; then
    log "Installing Microsoft apt signing key."
    curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | sudo gpg --dearmor -o /etc/apt/keyrings/microsoft.asc
    sudo chmod a+r /etc/apt/keyrings/microsoft.asc
  fi

  arch="$(dpkg --print-architecture)"
  codename="$(lsb_release -cs)"
  repo_line="deb [arch=${arch} signed-by=/etc/apt/keyrings/microsoft.asc] https://packages.microsoft.com/repos/azure-cli/ ${codename} main"
  printf '%s\n' "${repo_line}" | sudo tee /etc/apt/sources.list.d/azure-cli.list >/dev/null
}

install_azure_cli() {
  install_microsoft_repo
  apt_get_safe update
  apt_get_safe install -y azure-cli
}

main() {
  log "$0 is running from: ${DIR}"

  [[ "$(uname -s)" == "Linux" ]] || fail "This installer is intended for Linux/WSL Ubuntu."
  [[ -f /etc/os-release ]] || fail "Missing /etc/os-release."

  require_cmd sudo
  require_cmd apt-get

  if command -v az >/dev/null 2>&1; then
    log "Azure CLI already available: $(az version --query '\"azure-cli\"' -o tsv 2>/dev/null || az --version | sed -n '1p')"
    return
  fi

  ensure_base_packages
  install_azure_cli

  command -v az >/dev/null 2>&1 || fail "Azure CLI installation completed but az is not on PATH."
  log "Azure CLI installed: $(az version --query '\"azure-cli\"' -o tsv 2>/dev/null || az --version | sed -n '1p')"

  cat <<'EOF'

Next step:
  az login --use-device-code --allow-no-subscriptions --tenant 2c68be09-9050-4eac-8e39-041aa5b33803

EOF
}

main "$@"
