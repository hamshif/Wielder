#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${DIR}/install_apt_helpers.sh"

log() {
  printf '[install-docker] %s\n' "$*"
}

fail() {
  printf '[install-docker] ERROR: %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  local cmd="$1"
  command -v "$cmd" >/dev/null 2>&1 || fail "Required command not found: ${cmd}"
}

docker_cli_path() {
  command -v docker 2>/dev/null || true
}

docker_cli_usable() {
  local docker_path
  docker_path="$(docker_cli_path)"
  [[ -n "${docker_path}" ]] || return 1

  if [[ "${docker_path}" == /mnt/c/* || "${docker_path}" == /mnt/[a-zA-Z]/* ]]; then
    log "Ignoring Windows Docker Desktop shim on PATH: ${docker_path}"
    return 1
  fi

  docker --version >/dev/null 2>&1
}

docker_ok() {
  docker_cli_usable && (docker info >/dev/null 2>&1 || sudo docker info >/dev/null 2>&1)
}

docker_version_line() {
  if docker_cli_usable; then
    docker version --format '{{.Client.Version}}' 2>/dev/null || sudo docker version --format '{{.Client.Version}}' 2>/dev/null || true
  fi
}

docker_buildx_ok() {
  docker_cli_usable && (docker buildx version >/dev/null 2>&1 || sudo docker buildx version >/dev/null 2>&1)
}

ensure_base_packages() {
  apt_get_safe update
  apt_get_safe install -y ca-certificates curl gnupg util-linux-extra
}

cleanup_docker_repo() {
  sudo rm -f /etc/apt/sources.list.d/docker.list
  sudo rm -f /etc/apt/sources.list.d/docker.sources
  sudo rm -f /etc/apt/keyrings/docker.asc
}

install_docker_repo() {
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo tee /etc/apt/keyrings/docker.asc >/dev/null
  sudo chmod a+r /etc/apt/keyrings/docker.asc

  local arch codename
  arch="$(dpkg --print-architecture)"
  codename="$(. /etc/os-release && printf '%s' "${UBUNTU_CODENAME:-$VERSION_CODENAME}")"
  sudo rm -f /etc/apt/sources.list.d/docker.list
  sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${codename}
Components: stable
Architectures: ${arch}
Signed-By: /etc/apt/keyrings/docker.asc
EOF
}

install_docker_packages() {
  apt_get_safe update
  apt_get_safe install -y \
    docker-ce \
    docker-ce-cli \
    containerd.io \
    docker-buildx-plugin \
    docker-compose-plugin
}

ensure_buildx_plugin() {
  if docker_buildx_ok; then
    log "Docker buildx plugin is already available."
    return
  fi

  log "Docker buildx plugin is missing. Installing docker-buildx-plugin."
  ensure_base_packages
  install_docker_repo
  apt_get_safe update
  apt_get_safe install -y docker-buildx-plugin

  if docker_buildx_ok; then
    log "Docker buildx plugin is now available: $(docker buildx version 2>/dev/null || sudo docker buildx version 2>/dev/null || true)"
    return
  fi

  fail "Docker buildx plugin is still unavailable after installation."
}

ensure_docker_group() {
  if getent group docker >/dev/null 2>&1; then
    :
  else
    sudo groupadd docker
  fi

  if id -nG "${USER}" | tr ' ' '\n' | grep -qx docker; then
    log "User [${USER}] is already in the docker group."
  else
    log "Adding user [${USER}] to the docker group."
    sudo usermod -aG docker "${USER}"
  fi
}

start_docker_daemon() {
  if command -v systemctl >/dev/null 2>&1 && [[ -d /run/systemd/system ]]; then
    log "systemd detected. Enabling and starting docker.service."
    sudo systemctl enable docker >/dev/null 2>&1 || true
    sudo systemctl start docker
    return
  fi

  if command -v service >/dev/null 2>&1; then
    log "service detected. Starting docker."
    sudo service docker start || true
  fi
}

main() {
  log "$0 is running from: ${DIR}"

  [[ "$(uname -s)" == "Linux" ]] || fail "This installer is intended for Linux/WSL Ubuntu."
  [[ -f /etc/os-release ]] || fail "Missing /etc/os-release."

  require_cmd sudo
  require_cmd apt-get

  local force_reinstall="${FORCE_REINSTALL:-0}"
  if docker_cli_usable && docker_ok && [[ "${force_reinstall}" != "1" ]]; then
    log "Existing docker CLI detected: $(docker --version 2>/dev/null || sudo docker --version 2>/dev/null || true)"
    log "Docker daemon is already reachable. Skipping Docker installation and service changes."
  else
    cleanup_docker_repo
    ensure_base_packages

    if docker_cli_usable && [[ "${force_reinstall}" != "1" ]]; then
      log "Existing docker CLI detected: $(docker --version 2>/dev/null || sudo docker --version 2>/dev/null || true)"
      log "Docker is already installed. Skipping package installation."
    else
      install_docker_repo
      install_docker_packages
    fi

    ensure_docker_group
    start_docker_daemon
  fi

  ensure_buildx_plugin

  if docker_ok; then
    log "Installed Docker CLI: Docker version $(docker_version_line)"
    log "Docker daemon is reachable."
  else
    fail "Docker daemon is not reachable after installation."
  fi

  cat <<EOF

Next steps:
  1. Close and reopen the WSL shell so the new docker group membership takes effect.
     Or, if available, run:
       newgrp docker

     If newgrp is unavailable, install the account/session helper package:
       sudo apt-get install -y util-linux-extra

  2. Verify the engine:
       docker info

  3. If the daemon is still not running and systemd is enabled in WSL, run:
       sudo systemctl restart docker

  4. If systemd is not enabled in this WSL distro, start the daemon manually in one shell:
       sudo dockerd

EOF

  if command -v nvidia-ctk >/dev/null 2>&1; then
    cat <<'EOF'
  5. NVIDIA Container Toolkit is already installed. Verify GPU containers:
       docker run --rm --gpus all nvidia/cuda:12.6.3-base-ubuntu24.04 sh -lc 'nvidia-smi -L'
EOF
  else
    cat <<EOF
  5. For local GPU containers, install the NVIDIA Container Toolkit next:
       ${DIR}/install_nvidia_container_toolkit_wsl_ubuntu.sh
EOF
  fi
}

main "$@"
