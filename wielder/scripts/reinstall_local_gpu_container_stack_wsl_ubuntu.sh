#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() {
  printf '[reinstall-gpu-stack] %s\n' "$*"
}

fail() {
  printf '[reinstall-gpu-stack] ERROR: %s\n' "$*" >&2
  exit 1
}

main() {
  log "$0 is running from: ${DIR}"

  [[ "$(uname -s)" == "Linux" ]] || fail "This installer is intended for Linux/WSL Ubuntu."

  local nested="${ENABLE_NESTED_GPU_HANDOFF:-1}"

  log "Force-reinstalling Docker from the sanctioned repo installer."
  FORCE_REINSTALL=1 "${DIR}/install_docker_wsl_ubuntu.sh"

  log "Force-reinstalling NVIDIA Container Toolkit with nested GPU handoff=${nested}."
  FORCE_REINSTALL=1 ENABLE_NESTED_GPU_HANDOFF="${nested}" \
    "${DIR}/install_nvidia_container_toolkit_wsl_ubuntu.sh"

  cat <<EOF

Reinstalled the local GPU container stack from the sanctioned repo scripts.

Verification:
  docker version
  docker buildx version
  docker run --rm --gpus all nvidia/cuda:12.6.3-base-ubuntu24.04 sh -lc 'nvidia-smi -L'

Optional next step:
  ${DIR}/install_k3d_wsl_ubuntu.sh

EOF
}

main "$@"
