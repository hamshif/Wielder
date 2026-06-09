#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="/usr/local/bin:${PATH}"
source "${DIR}/install_apt_helpers.sh"

KIND_VERSION="${KIND_VERSION:-v0.31.0}"
KIND_CLUSTER_NAME="${KIND_CLUSTER_NAME:-kind-hybrid}"
KIND_NODE_IMAGE="${KIND_NODE_IMAGE:-kindest/node:v1.31.9}"
KIND_NODEPORTS="${KIND_NODEPORTS:-32000 32051}"
KIND_REGISTRY_NAME="${KIND_REGISTRY_NAME:-kind-registry}"
KIND_REGISTRY_HOST_PORT="${KIND_REGISTRY_HOST_PORT:-5100}"
KIND_REGISTRY_CLUSTER_BINDING="${KIND_REGISTRY_CLUSTER_BINDING:-kind-registry:5000}"
CREATE_CLUSTER="${CREATE_CLUSTER:-1}"
RECREATE_CLUSTER="${RECREATE_CLUSTER:-1}"
LOCAL_BUCKETS_ROOT="${LOCAL_BUCKETS_ROOT:-${HOME}/local_buckets/workspace}"
export KIND_VERSION
export KIND_CLUSTER_NAME
export KIND_NODE_IMAGE
export KIND_NODEPORTS
export KIND_REGISTRY_NAME
export KIND_REGISTRY_HOST_PORT
export KIND_REGISTRY_CLUSTER_BINDING
export CREATE_CLUSTER
export RECREATE_CLUSTER
export LOCAL_BUCKETS_ROOT

log() {
  printf '[install-kind] %s\n' "$*"
}

fail() {
  printf '[install-kind] ERROR: %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  local cmd="$1"
  command -v "$cmd" >/dev/null 2>&1 || fail "Required command not found: ${cmd}"
}

docker_access_ok() {
  docker info >/dev/null 2>&1
}

user_in_docker_group_file() {
  getent group docker | awk -F: '{print $4}' | tr ',' '\n' | grep -qx "${USER}"
}

quote_command() {
  printf '%q ' "$@"
}

ensure_docker_group_session() {
  docker_access_ok && return

  if command -v sg >/dev/null 2>&1 && user_in_docker_group_file; then
    if sg docker -c 'docker info >/dev/null 2>&1'; then
      log "Current shell has not picked up docker group membership; re-running kind setup under group [docker]."
      exec sg docker -c "$(quote_command "$0" "$@")"
    fi
  fi

  fail "Docker is installed, but the current session cannot reach /var/run/docker.sock. Open a new shell or run newgrp docker, then retry."
}

ensure_curl() {
  if command -v curl >/dev/null 2>&1; then
    return
  fi

  log "curl not found. Installing curl via apt-get."
  apt_get_safe update
  apt_get_safe install -y curl ca-certificates
}

install_kind() {
  ensure_curl

  local tmp_dir
  tmp_dir="$(mktemp -d)"
  local force_reinstall="${FORCE_REINSTALL:-0}"

  if command -v kind >/dev/null 2>&1 && kind version 2>/dev/null | grep -Fq "${KIND_VERSION}" && [[ "${force_reinstall}" != "1" ]]; then
    log "Existing kind already matches ${KIND_VERSION}. Skipping reinstall."
    rm -rf "${tmp_dir}"
    return
  fi

  if command -v kind >/dev/null 2>&1; then
    log "Replacing existing kind: $(kind version 2>/dev/null || true)"
  else
    log "Installing kind ${KIND_VERSION}."
  fi

  if ! curl -fsSL -o "${tmp_dir}/kind" "https://kind.sigs.k8s.io/dl/${KIND_VERSION}/kind-linux-amd64"; then
    rm -rf "${tmp_dir}"
    fail "Failed to download kind ${KIND_VERSION}."
  fi

  chmod +x "${tmp_dir}/kind"
  sudo mv "${tmp_dir}/kind" /usr/local/bin/kind
  rm -rf "${tmp_dir}"
  log "Installed: $(kind version)"
}

kind_cluster_exists() {
  kind get clusters 2>/dev/null | grep -qx "${KIND_CLUSTER_NAME}"
}

ensure_kind_registry() {
  if docker ps -a --format '{{.Names}}' | grep -qx "${KIND_REGISTRY_NAME}"; then
    if ! docker ps --format '{{.Names}}' | grep -qx "${KIND_REGISTRY_NAME}"; then
      log "Starting existing kind registry container [${KIND_REGISTRY_NAME}]."
      docker start "${KIND_REGISTRY_NAME}" >/dev/null
    else
      log "kind registry [${KIND_REGISTRY_NAME}] already exists."
    fi
    return
  fi

  log "Creating kind registry [${KIND_REGISTRY_NAME}] on localhost:${KIND_REGISTRY_HOST_PORT}."
  docker run -d \
    --restart=always \
    -p "127.0.0.1:${KIND_REGISTRY_HOST_PORT}:5000" \
    --name "${KIND_REGISTRY_NAME}" \
    registry:2 >/dev/null
}

connect_registry_to_kind_network() {
  if ! docker network inspect kind >/dev/null 2>&1; then
    fail "Expected Docker network [kind] was not created."
  fi

  if docker network inspect kind --format '{{json .Containers}}' | grep -Fq "\"Name\":\"${KIND_REGISTRY_NAME}\""; then
    log "kind registry [${KIND_REGISTRY_NAME}] is already connected to the [kind] network."
    return
  fi

  log "Connecting kind registry [${KIND_REGISTRY_NAME}] to the [kind] network."
  docker network connect kind "${KIND_REGISTRY_NAME}"
}

publish_local_registry_config() {
  local kube_context="kind-${KIND_CLUSTER_NAME}"
  kubectl --context "${kube_context}" apply -f - <<EOF >/dev/null
apiVersion: v1
kind: ConfigMap
metadata:
  name: local-registry-hosting
  namespace: kube-public
data:
  localRegistryHosting.v1: |
    host: "localhost:${KIND_REGISTRY_HOST_PORT}"
    help: "https://kind.sigs.k8s.io/docs/user/local-registry/"
EOF
}

write_kind_config() {
  local config_path="$1"

  {
    cat <<EOF
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: ${KIND_CLUSTER_NAME}
containerdConfigPatches:
- |-
  [plugins."io.containerd.grpc.v1.cri".registry.mirrors."${KIND_REGISTRY_CLUSTER_BINDING}"]
    endpoint = ["http://${KIND_REGISTRY_CLUSTER_BINDING}"]
nodes:
- role: control-plane
  image: ${KIND_NODE_IMAGE}
  extraMounts:
  - hostPath: ${LOCAL_BUCKETS_ROOT}
    containerPath: ${LOCAL_BUCKETS_ROOT}
  extraPortMappings:
EOF
    local port
    for port in ${KIND_NODEPORTS}; do
      cat <<EOF
  - containerPort: ${port}
    hostPort: ${port}
    listenAddress: "127.0.0.1"
    protocol: TCP
EOF
    done
    cat <<EOF
- role: worker
  image: ${KIND_NODE_IMAGE}
  extraMounts:
  - hostPath: ${LOCAL_BUCKETS_ROOT}
    containerPath: ${LOCAL_BUCKETS_ROOT}
EOF
  } > "${config_path}"
}

create_kind_cluster() {
  if kind_cluster_exists; then
    if [[ "${RECREATE_CLUSTER}" == "1" ]]; then
      log "Deleting existing kind cluster [${KIND_CLUSTER_NAME}] before recreation."
      kind delete cluster --name "${KIND_CLUSTER_NAME}"
    else
      log "kind cluster [${KIND_CLUSTER_NAME}] already exists. Skipping create."
      return
    fi
  fi

  local config_path
  config_path="$(mktemp)"
  write_kind_config "${config_path}"

  log "Creating kind cluster [${KIND_CLUSTER_NAME}] with node image [${KIND_NODE_IMAGE}]."
  if ! kind create cluster --name "${KIND_CLUSTER_NAME}" --image "${KIND_NODE_IMAGE}" --config "${config_path}"; then
    rm -f "${config_path}"
    fail "kind cluster creation failed for [${KIND_CLUSTER_NAME}]."
  fi

  rm -f "${config_path}"
}

main() {
  log "$0 is running from: ${DIR}"

  [[ "$(uname -s)" == "Linux" ]] || fail "This installer is intended for Linux/WSL Ubuntu."

  require_cmd sudo
  require_cmd apt-get

  mkdir -p "${LOCAL_BUCKETS_ROOT}"

  "${DIR}/install_docker_wsl_ubuntu.sh"
  install_kind
  ensure_docker_group_session "$@"
  ensure_kind_registry

  if [[ "${CREATE_CLUSTER}" == "1" ]]; then
    create_kind_cluster
    connect_registry_to_kind_network
    publish_local_registry_config
  fi

  cat <<EOF

Completed:
  - Docker configured for kind
  - kind installed
  - kind cluster target: ${KIND_CLUSTER_NAME}
  - node image: ${KIND_NODE_IMAGE}

Useful commands:
  kind get clusters
  kubectl config get-contexts
  kubectl --context kind-${KIND_CLUSTER_NAME} get nodes

To load a locally built image into kind:
  kind load docker-image <image:tag> --name ${KIND_CLUSTER_NAME}

Local registry:
  push: localhost:${KIND_REGISTRY_HOST_PORT}
  pull from kind nodes: ${KIND_REGISTRY_CLUSTER_BINDING}

EOF
}

main "$@"
