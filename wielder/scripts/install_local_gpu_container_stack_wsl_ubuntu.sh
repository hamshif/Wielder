#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() {
  printf '[install-gpu-stack] %s\n' "$*"
}

fail() {
  printf '[install-gpu-stack] ERROR: %s\n' "$*" >&2
  exit 1
}

main() {
  log "$0 is running from: ${DIR}"

  [[ "$(uname -s)" == "Linux" ]] || fail "This installer is intended for Linux/WSL Ubuntu."

  local nested="${ENABLE_NESTED_GPU_HANDOFF:-1}"

  "${DIR}/install_docker_wsl_ubuntu.sh"
  ENABLE_NESTED_GPU_HANDOFF="${nested}" "${DIR}/install_nvidia_container_toolkit_wsl_ubuntu.sh"

  cat <<EOF

Local GPU container stack is ready.

Use this to verify again:
  docker run --rm --gpus all nvidia/cuda:12.6.3-base-ubuntu24.04 sh -lc 'nvidia-smi -L'

EOF

  if [[ "${nested}" == "1" ]]; then
    cat <<EOF
Nested k3d/kind GPU handoff is also configured and verified.
EOF
  else
    cat <<EOF
Nested k3d/kind GPU handoff was skipped.
EOF
  fi
}

main "$@"
