#!/bin/bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

log() {
  printf '[install-k3d] %s\n' "$*"
}

fail() {
  printf '[install-k3d] ERROR: %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  local cmd="$1"
  command -v "$cmd" >/dev/null 2>&1 || fail "Required command not found: ${cmd}"
}

ensure_curl() {
  if command -v curl >/dev/null 2>&1; then
    return
  fi

  log "curl not found. Installing curl via apt-get."
  sudo apt-get update
  sudo apt-get install -y curl ca-certificates
}

main() {
  if [[ "$(uname -s)" != "Linux" ]]; then
    fail "This installer is intended for Linux/WSL Ubuntu."
  fi

  ensure_curl
  require_cmd sudo
  require_cmd docker

  log "$0 is running from: ${DIR}"

  if ! docker info >/dev/null 2>&1; then
    fail "Docker daemon is not reachable. Start Docker Desktop first and verify 'docker info' works in WSL."
  fi

  local desired_version="${K3D_VERSION:-}"
  if command -v k3d >/dev/null 2>&1; then
    log "Existing k3d detected: $(k3d version 2>/dev/null | head -n 1 || true)"
  else
    log "No existing k3d installation detected."
  fi

  if [[ -n "${desired_version}" ]]; then
    log "Installing k3d version ${desired_version}."
    curl -fsSL "https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh" | TAG="${desired_version}" bash
  else
    log "Installing latest k3d release."
    curl -fsSL "https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh" | bash
  fi

  require_cmd k3d

  log "Installed: $(k3d version | head -n 1)"

  if command -v kubectl >/dev/null 2>&1; then
    log "kubectl detected: $(kubectl version --client 2>/dev/null | head -n 1 || true)"
  else
    log "kubectl is not installed. k3d can still create clusters, but kubectl will be needed to inspect them."
  fi

  cat <<'EOF'

Next steps:
  1. Create a cluster with a managed registry, for example:
     k3d cluster create k3d --registry-create k3d-registry.localhost:0.0.0.0:5000
  2. Confirm contexts:
     kubectl config get-contexts
  3. Point the `k3d_hybrid_model_binding` ecosystem at the resulting k3d kube context.

EOF
}

main "$@"
