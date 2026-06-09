#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${DIR}/install_apt_helpers.sh"
CUDA_SMOKE_IMAGE="${CUDA_SMOKE_IMAGE:-nvidia/cuda:12.6.3-base-ubuntu24.04}"
CUDA_SMOKE_SHELL="${CUDA_SMOKE_SHELL:-nvidia-smi -L}"

log() {
  printf '[install-nvidia] %s\n' "$*"
}

fail() {
  printf '[install-nvidia] ERROR: %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  local cmd="$1"
  command -v "$cmd" >/dev/null 2>&1 || fail "Required command not found: ${cmd}"
}

docker_run() {
  if docker info >/dev/null 2>&1; then
    docker "$@"
  else
    sudo docker "$@"
  fi
}

ensure_base_packages() {
  apt_get_safe update
  apt_get_safe install -y ca-certificates curl gnupg
}

install_nvidia_repo() {
  sudo install -m 0755 -d /usr/share/keyrings
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
    sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null
}

install_nvidia_packages() {
  apt_get_safe update
  apt_get_safe install -y nvidia-container-toolkit
}

restart_docker() {
  if command -v systemctl >/dev/null 2>&1 && [[ -d /run/systemd/system ]]; then
    sudo systemctl restart docker
    return
  fi

  if command -v service >/dev/null 2>&1; then
    sudo service docker restart
    return
  fi

  fail "Could not find a supported way to restart Docker."
}

disable_docker_cdi_for_wsl() {
  require_cmd python3
  log "Ensuring Docker CDI mode is disabled for WSL."
  sudo python3 - <<'PY'
import json
from pathlib import Path

path = Path("/etc/docker/daemon.json")
if path.exists():
    data = json.loads(path.read_text())
else:
    data = {}

features = data.get("features", {})
features.pop("cdi", None)
if features:
    data["features"] = features
else:
    data.pop("features", None)

path.write_text(json.dumps(data, indent=4) + "\n")
PY
}

run_gpu_smoke() {
  log "Running Docker GPU smoke test."
  docker_run run --rm --gpus all "${CUDA_SMOKE_IMAGE}" sh -lc "${CUDA_SMOKE_SHELL}"
}

run_nested_handoff_smoke() {
  log "Running nested GPU handoff smoke test for k3d/kind."
  docker_run run --rm --runtime nvidia \
    -v /dev/null:/var/run/nvidia-container-devices/all \
    "${CUDA_SMOKE_IMAGE}" sh -lc "${CUDA_SMOKE_SHELL}"
}

verify_wsl_gpu_visibility() {
  log "Checking native WSL GPU visibility before Docker runtime setup."
  local gpu_list
  if gpu_list="$(nvidia-smi -L 2>&1)"; then
    printf '%s\n' "${gpu_list}"
    return
  fi

  fail "Native WSL GPU access is not healthy: ${gpu_list}

This is below Docker and kind.
Fix the WSL GPU first, then rerun:
  1. From Windows PowerShell: wsl --shutdown
  2. Reopen WSL and run: nvidia-smi -L
  3. If it still fails, check the Windows NVIDIA driver / reboot Windows."
}

main() {
  log "$0 is running from: ${DIR}"

  [[ "$(uname -s)" == "Linux" ]] || fail "This installer is intended for Linux/WSL Ubuntu."

  require_cmd sudo
  require_cmd apt-get
  require_cmd docker
  require_cmd nvidia-smi
  ensure_base_packages
  verify_wsl_gpu_visibility

  local force_reinstall="${FORCE_REINSTALL:-0}"
  local nested="${ENABLE_NESTED_GPU_HANDOFF:-0}"

  if command -v nvidia-ctk >/dev/null 2>&1 && [[ "${force_reinstall}" != "1" ]]; then
    log "Existing nvidia-ctk detected: $(nvidia-ctk --version 2>/dev/null || true)"
    log "NVIDIA Container Toolkit is already installed. Skipping package installation."
  else
    install_nvidia_repo
    install_nvidia_packages
  fi

  require_cmd nvidia-ctk

  if [[ "${nested}" == "1" ]]; then
    log "Configuring Docker runtime with NVIDIA as default for nested k3d/kind handoff."
    sudo nvidia-ctk runtime configure --runtime=docker --set-as-default
  else
    log "Configuring Docker runtime for direct GPU containers."
    sudo nvidia-ctk runtime configure --runtime=docker
  fi

  log "Forcing NVIDIA runtime mode to legacy for WSL."
  sudo nvidia-ctk config --set nvidia-container-runtime.mode=legacy --in-place
  disable_docker_cdi_for_wsl
  restart_docker
  run_gpu_smoke

  if [[ "${nested}" == "1" ]]; then
    run_nested_handoff_smoke
  fi

  cat <<EOF

Completed:
  - NVIDIA Container Toolkit installed and configured
  - Docker restarted
  - Local GPU container smoke test passed

Direct GPU container check:
  docker run --rm --gpus all ${CUDA_SMOKE_IMAGE} sh -lc '${CUDA_SMOKE_SHELL}'

EOF

  if [[ "${nested}" == "1" ]]; then
    cat <<EOF
Nested k3d/kind handoff check:
  docker run --rm --runtime nvidia -v /dev/null:/var/run/nvidia-container-devices/all ${CUDA_SMOKE_IMAGE} sh -lc '${CUDA_SMOKE_SHELL}'
EOF
  else
    cat <<'EOF'
To enable nested k3d/kind handoff as well, rerun:
  ENABLE_NESTED_GPU_HANDOFF=1 ./install_nvidia_container_toolkit_wsl_ubuntu.sh
EOF
  fi
}

main "$@"
