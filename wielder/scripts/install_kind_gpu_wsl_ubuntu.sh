#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="/usr/local/bin:${PATH}"
source "${DIR}/install_apt_helpers.sh"
CUDA_SMOKE_IMAGE="${CUDA_SMOKE_IMAGE:-nvidia/cuda:12.6.3-base-ubuntu24.04}"
CUDA_SMOKE_SHELL="${CUDA_SMOKE_SHELL:-nvidia-smi -L}"
KIND_VERSION="${KIND_VERSION:-v0.31.0}"
NVKIND_VERSION="${NVKIND_VERSION:-latest}"
KIND_CLUSTER_NAME="${KIND_CLUSTER_NAME:-kind-gpu}"
KIND_NODE_IMAGE="${KIND_NODE_IMAGE:-kindest/node:v1.31.9}"
KIND_NODEPORTS="${KIND_NODEPORTS-}"
KIND_REGISTRY_NAME="${KIND_REGISTRY_NAME:-kind-registry}"
KIND_REGISTRY_HOST_PORT="${KIND_REGISTRY_HOST_PORT:-5100}"
KIND_REGISTRY_CLUSTER_BINDING="${KIND_REGISTRY_CLUSTER_BINDING:-kind-registry:5000}"
CREATE_CLUSTER="${CREATE_CLUSTER:-1}"
INSTALL_DEVICE_PLUGIN="${INSTALL_DEVICE_PLUGIN:-1}"
VERIFY_GPU_ALLOCATABLE="${VERIFY_GPU_ALLOCATABLE:-1}"
RECREATE_CLUSTER="${RECREATE_CLUSTER:-1}"
LOCAL_BUCKETS_ROOT="${LOCAL_BUCKETS_ROOT:-${HOME}/local_buckets/workspace}"
REINSTALL_KIND_TOOLS="${REINSTALL_KIND_TOOLS:-0}"

log() {
  printf '[install-kind-gpu] %s\n' "$*"
}

fail() {
  printf '[install-kind-gpu] ERROR: %s\n' "$*" >&2
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
  apt_get_safe update
  apt_get_safe install -y curl ca-certificates
}

ensure_go() {
  if command -v go >/dev/null 2>&1; then
    return
  fi

  log "go not found. Installing golang-go via apt-get."
  apt_get_safe update
  apt_get_safe install -y golang-go
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

docker_run() {
  if docker info >/dev/null 2>&1; then
    docker "$@"
  else
    sudo docker "$@"
  fi
}

configure_nvidia_for_kind() {
  require_cmd nvidia-ctk

  log "Configuring Docker runtime for nested GPU handoff in kind."
  sudo nvidia-ctk runtime configure --runtime=docker --set-as-default
  sudo nvidia-ctk config --set accept-nvidia-visible-devices-as-volume-mounts=true --in-place
  restart_docker
}

verify_nested_handoff() {
  log "Verifying nested GPU handoff via volume-mount injection."
  docker_run run --rm --runtime nvidia \
    -v /dev/null:/var/run/nvidia-container-devices/all \
    "${CUDA_SMOKE_IMAGE}" sh -lc "${CUDA_SMOKE_SHELL}"
}

host_nested_handoff_healthy() {
  docker_run run --rm --runtime nvidia \
    -v /dev/null:/var/run/nvidia-container-devices/all \
    "${CUDA_SMOKE_IMAGE}" sh -lc "${CUDA_SMOKE_SHELL}" >/dev/null 2>&1
}

ensure_host_nested_gpu_handoff() {
  if host_nested_handoff_healthy; then
    log "Existing Docker/NVIDIA nested GPU handoff is healthy. Skipping host GPU stack install and Docker reconfiguration."
    return
  fi

  log "Docker/NVIDIA nested GPU handoff is not healthy yet. Installing/configuring host GPU container stack."
  ENABLE_NESTED_GPU_HANDOFF=1 "${DIR}/install_local_gpu_container_stack_wsl_ubuntu.sh"
  configure_nvidia_for_kind
  verify_nested_handoff
}

install_kind() {
  if command -v kind >/dev/null 2>&1 && [[ "${REINSTALL_KIND_TOOLS}" != "1" ]]; then
    log "Existing kind detected: $(kind version 2>/dev/null || true). Skipping kind reinstall."
    return
  fi

  ensure_curl

  local tmp_dir
  tmp_dir="$(mktemp -d)"

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

install_nvkind() {
  if command -v nvkind >/dev/null 2>&1 && [[ "${REINSTALL_KIND_TOOLS}" != "1" ]]; then
    log "Existing nvkind detected at $(command -v nvkind). Skipping nvkind reinstall."
    return
  fi

  ensure_go
  require_cmd python3

  local tmp_dir
  tmp_dir="$(mktemp -d)"

  log "Installing patched nvkind @ ${NVKIND_VERSION}."
  if ! git clone --depth 1 https://github.com/NVIDIA/nvkind "${tmp_dir}/nvkind" >/dev/null 2>&1; then
    rm -rf "${tmp_dir}"
    fail "Failed to clone nvkind."
  fi

  if ! python3 - <<'PY' "${tmp_dir}/nvkind/pkg/nvkind/node.go"
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()
old = """func (n *Node) PatchProcDriverNvidia() error {\n\t// Unmount the masked /proc/driver/nvidia to allow dynamically generated\n\t// MIG devices to be discovered\n\terr := n.runScript(`\n\t\tumount -R /proc/driver/nvidia\n\t`)\n\tif err != nil {\n\t\treturn fmt.Errorf(\"running script on %v: %w\", n.Name, err)\n\t}\n\n\t// Make it so that calls into nvidia-smi / libnvidia-ml.so do not attempt\n\t// to recreate device nodes or reset their permissions if tampered with\n\terr = n.runScript(`\n\t\tcp /proc/driver/nvidia/params root/gpu-params\n\t\tsed -i 's/^ModifyDeviceFiles: 1$/ModifyDeviceFiles: 0/' root/gpu-params\n\t\tmount --bind root/gpu-params /proc/driver/nvidia/params\n\t`)\n\tif err != nil {\n\t\treturn fmt.Errorf(\"running script on %v: %w\", n.Name, err)\n\t}\n"""
new = """func (n *Node) PatchProcDriverNvidia() error {\n\t// WSL-backed kind nodes can expose NVML and nvidia-smi without surfacing\n\t// /proc/driver/nvidia. Skip the procfs patching path entirely in that case.\n\terr := n.runScript(`\n\t\tif [ ! -d /proc/driver/nvidia ]; then\n\t\t\texit 0\n\t\tfi\n\t\tumount -R /proc/driver/nvidia || true\n\t\tif [ ! -f /proc/driver/nvidia/params ]; then\n\t\t\texit 0\n\t\tfi\n\t\tcp /proc/driver/nvidia/params root/gpu-params\n\t\tsed -i 's/^ModifyDeviceFiles: 1$/ModifyDeviceFiles: 0/' root/gpu-params\n\t\tmount --bind root/gpu-params /proc/driver/nvidia/params\n\t`)\n\tif err != nil {\n\t\treturn fmt.Errorf(\"running script on %v: %w\", n.Name, err)\n\t}\n"""
if old not in text:
    raise SystemExit("Expected nvkind PatchProcDriverNvidia block not found")
path.write_text(text.replace(old, new))
PY
  then
    rm -rf "${tmp_dir}"
    fail "Failed to patch nvkind for WSL procfs handling."
  fi

  if ! (cd "${tmp_dir}/nvkind" && go build -o "${tmp_dir}/nvkind.bin" ./cmd/nvkind); then
    rm -rf "${tmp_dir}"
    fail "Failed to build nvkind."
  fi
  sudo install -m 0755 "${tmp_dir}/nvkind.bin" /usr/local/bin/nvkind
  rm -rf "${tmp_dir}"
  command -v nvkind >/dev/null 2>&1 || fail "nvkind installation succeeded but nvkind is not on PATH."
  log "Installed nvkind at $(command -v nvkind)"
}

kind_cluster_exists() {
  kind get clusters 2>/dev/null | grep -qx "${KIND_CLUSTER_NAME}"
}

ensure_kind_registry() {
  if docker_run ps -a --format '{{.Names}}' | grep -qx "${KIND_REGISTRY_NAME}"; then
    if ! docker_run ps --format '{{.Names}}' | grep -qx "${KIND_REGISTRY_NAME}"; then
      log "Starting existing kind registry container [${KIND_REGISTRY_NAME}]."
      docker_run start "${KIND_REGISTRY_NAME}" >/dev/null
    else
      log "kind registry [${KIND_REGISTRY_NAME}] already exists."
    fi
    return
  fi

  log "Creating kind registry [${KIND_REGISTRY_NAME}] on localhost:${KIND_REGISTRY_HOST_PORT}."
  docker_run run -d \
    --restart=always \
    -p "127.0.0.1:${KIND_REGISTRY_HOST_PORT}:5000" \
    --name "${KIND_REGISTRY_NAME}" \
    registry:2 >/dev/null
}

connect_registry_to_kind_network() {
  if ! docker_run network inspect kind >/dev/null 2>&1; then
    fail "Expected Docker network [kind] was not created."
  fi

  if docker_run network inspect kind --format '{{json .Containers}}' | grep -Fq "\"Name\":\"${KIND_REGISTRY_NAME}\""; then
    log "kind registry [${KIND_REGISTRY_NAME}] is already connected to the [kind] network."
    return
  fi

  log "Connecting kind registry [${KIND_REGISTRY_NAME}] to the [kind] network."
  docker_run network connect kind "${KIND_REGISTRY_NAME}"
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

configure_kind_node_registry() {
  local nodes
  nodes="$(docker_run ps --format '{{.Names}}' | grep -E "^${KIND_CLUSTER_NAME}-(control-plane|worker)" || true)"
  [[ -n "${nodes}" ]] || fail "No kind node containers found for [${KIND_CLUSTER_NAME}]."

  local node
  while IFS= read -r node; do
    [[ -n "${node}" ]] || continue
    log "Configuring local HTTP registry trust inside kind node [${node}]."
    docker_run exec "${node}" bash -lc "
      set -euo pipefail
      mkdir -p /etc/containerd/conf.d /etc/containerd/certs.d/${KIND_REGISTRY_CLUSTER_BINDING}
      cat >/etc/containerd/certs.d/${KIND_REGISTRY_CLUSTER_BINDING}/hosts.toml <<'EOF'
server = \"http://${KIND_REGISTRY_CLUSTER_BINDING}\"

[host.\"http://${KIND_REGISTRY_CLUSTER_BINDING}\"]
  capabilities = [\"pull\", \"resolve\", \"push\"]
EOF
      cat >/etc/containerd/conf.d/10-kind-registry.toml <<'EOF'
version = 3

[plugins.\"io.containerd.cri.v1.images\".registry]
  config_path = \"/etc/containerd/certs.d\"
EOF
      systemctl restart containerd || service containerd restart || pkill -HUP containerd
    "
  done <<< "${nodes}"
}

write_kind_config() {
  local config_path="$1"

  {
    cat <<EOF
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
containerdConfigPatches:
- |-
  [plugins."io.containerd.grpc.v1.cri".registry.mirrors."${KIND_REGISTRY_CLUSTER_BINDING}"]
    endpoint = ["http://${KIND_REGISTRY_CLUSTER_BINDING}"]
nodes:
- role: control-plane
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
    cat <<'EOF'
- role: worker
  extraMounts:
  - hostPath: /dev/null
    containerPath: /var/run/nvidia-container-devices/all
  kubeadmConfigPatches:
  - |
    kind: JoinConfiguration
    nodeRegistration:
      kubeletExtraArgs:
        node-labels: "nvidia.com/gpu.present=true"
EOF
  } > "${config_path}"
}

write_nvkind_template() {
  local template_path="$1"

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
  image: {{ \$.image }}
  kubeadmConfigPatches:
  - |
    kind: JoinConfiguration
    nodeRegistration:
      kubeletExtraArgs:
        node-labels: "nvidia.com/gpu.present=true"
  extraMounts:
    - hostPath: ${LOCAL_BUCKETS_ROOT}
      containerPath: ${LOCAL_BUCKETS_ROOT}
    # Inject every host GPU into the worker node using the nvkind mount convention.
    {{- range \$gpu := until numGPUs }}
    - hostPath: /dev/null
      containerPath: /var/run/nvidia-container-devices/{{ \$gpu }}
    {{- end }}
EOF
  } > "${template_path}"
}

create_kind_cluster() {
  require_cmd kubectl

  if kind_cluster_exists; then
    if [[ "${RECREATE_CLUSTER}" == "1" ]]; then
      log "Deleting existing kind cluster [${KIND_CLUSTER_NAME}] before recreation."
      kind delete cluster --name "${KIND_CLUSTER_NAME}"
    else
      log "kind cluster [${KIND_CLUSTER_NAME}] already exists. Skipping create."
      return
    fi
  fi

  local template_path
  local values_path
  template_path="$(mktemp)"
  values_path="$(mktemp)"
  write_nvkind_template "${template_path}"
  printf 'name: %s\nimage: %s\n' "${KIND_CLUSTER_NAME}" "${KIND_NODE_IMAGE}" > "${values_path}"

  log "Creating kind cluster [${KIND_CLUSTER_NAME}] via nvkind with node image [${KIND_NODE_IMAGE}]."
  if ! nvkind cluster create \
    --name "${KIND_CLUSTER_NAME}" \
    --image "${KIND_NODE_IMAGE}" \
    --config-template "${template_path}" \
    --config-values "${values_path}"; then
    rm -f "${template_path}" "${values_path}"
    fail "nvkind cluster creation failed for [${KIND_CLUSTER_NAME}]."
  fi

  rm -f "${template_path}" "${values_path}"
}

wait_for_kind_nodes_ready() {
  require_cmd kubectl

  local kube_context="kind-${KIND_CLUSTER_NAME}"
  log "Waiting for kind nodes in [${kube_context}] to become Ready."
  kubectl --context "${kube_context}" wait --for=condition=Ready nodes --all --timeout=180s
}

configure_kind_worker_nvidia_runtime() {
  local workers
  workers="$(docker_run ps --format '{{.Names}}' | grep -E "^${KIND_CLUSTER_NAME}-worker" || true)"
  [[ -n "${workers}" ]] || fail "No kind worker containers found for [${KIND_CLUSTER_NAME}]."

  local worker
  while IFS= read -r worker; do
    [[ -n "${worker}" ]] || continue
    log "Configuring NVIDIA runtime inside kind worker [${worker}]."
    docker_run exec "${worker}" bash -lc '
      set -euo pipefail
      command -v nvidia-ctk >/dev/null 2>&1 || {
        echo "nvidia-ctk is missing inside worker node" >&2
        exit 1
      }
      nvidia-ctk config \
        --set nvidia-container-runtime.mode=legacy \
        --set accept-nvidia-visible-devices-as-volume-mounts=true \
        --in-place
      systemctl restart containerd || service containerd restart || pkill -HUP containerd
    '
  done <<< "${workers}"
}

diagnose_nvidia_device_plugin() {
  require_cmd kubectl

  local kube_context="kind-${KIND_CLUSTER_NAME}"
  log "Diagnosing NVIDIA device plugin failure in [${kube_context}]."
  kubectl --context "${kube_context}" get nodes -o wide || true
  kubectl --context "${kube_context}" -n nvidia get pods -o wide || true
  kubectl --context "${kube_context}" -n nvidia logs -l app.kubernetes.io/name=nvidia-device-plugin --tail=200 || true
}

install_nvidia_device_plugin() {
  require_cmd kubectl
  require_cmd helm

  local kube_context="kind-${KIND_CLUSTER_NAME}"

  if ! kubectl config get-contexts "${kube_context}" >/dev/null 2>&1; then
    fail "Expected kube context [${kube_context}] was not created."
  fi

  log "Installing NVIDIA device plugin into [${kube_context}]."
  helm repo add nvdp https://nvidia.github.io/k8s-device-plugin >/dev/null 2>&1 || true
  helm repo update >/dev/null
  helm upgrade -i \
    --kube-context "${kube_context}" \
    --namespace nvidia \
    --create-namespace \
    --set runtimeClassName=nvidia \
    --set deviceListStrategy=volume-mounts \
    nvidia-device-plugin nvdp/nvidia-device-plugin

  local daemonset_name
  daemonset_name="$(kubectl --context "${kube_context}" -n nvidia get daemonset -o jsonpath='{.items[0].metadata.name}')"
  [[ -n "${daemonset_name}" ]] || fail "NVIDIA device plugin daemonset was not created."

  if ! kubectl --context "${kube_context}" -n nvidia rollout status "daemonset/${daemonset_name}" --timeout=180s; then
    diagnose_nvidia_device_plugin
    fail "NVIDIA device plugin rollout failed. The kind worker sees a GPU at the node level, but nested pods do not get a usable NVML view on this WSL setup."
  fi
}

verify_gpu_allocatable() {
  require_cmd kubectl

  local kube_context="kind-${KIND_CLUSTER_NAME}"
  local attempts=30
  local sleep_seconds=2
  local node_report=""
  local i

  for ((i=1; i<=attempts; i++)); do
    node_report="$(kubectl --context "${kube_context}" get nodes -o custom-columns=NAME:.metadata.name,GPU:.status.allocatable.nvidia\\.com/gpu --no-headers)"
    log "Node GPU allocatable report:"
    printf '%s\n' "${node_report}"

    if printf '%s\n' "${node_report}" | grep -E 'worker' | grep -Eq '[[:space:]][1-9][0-9]*$'; then
      return
    fi

    log "GPU allocatable not published yet. Waiting ${sleep_seconds}s (${i}/${attempts})."
    sleep "${sleep_seconds}"
  done

  fail "No allocatable GPUs were reported by the kind worker nodes."
}

verify_k8s_gpu_runtime() {
  require_cmd kubectl

  local kube_context="kind-${KIND_CLUSTER_NAME}"
  local smoke_name="kind-gpu-runtime-smoke"

  log "Running Kubernetes GPU runtime smoke test in [${kube_context}]."
  kubectl --context "${kube_context}" delete pod "${smoke_name}" --ignore-not-found --wait=true >/dev/null
  kubectl --context "${kube_context}" apply -f - <<EOF >/dev/null
apiVersion: v1
kind: Pod
metadata:
  name: ${smoke_name}
spec:
  restartPolicy: Never
  runtimeClassName: nvidia
  containers:
  - name: cuda-smoke
    image: ${CUDA_SMOKE_IMAGE}
    command: ["sh", "-lc", "${CUDA_SMOKE_SHELL} && sleep 5"]
    resources:
      limits:
        nvidia.com/gpu: 1
EOF

  if ! kubectl --context "${kube_context}" wait --for=condition=Ready "pod/${smoke_name}" --timeout=180s >/dev/null; then
    kubectl --context "${kube_context}" describe pod "${smoke_name}" || true
    kubectl --context "${kube_context}" logs "${smoke_name}" || true
    kubectl --context "${kube_context}" delete pod "${smoke_name}" --ignore-not-found --wait=false >/dev/null
    fail "Kubernetes GPU runtime smoke pod did not become Ready."
  fi

  if ! kubectl --context "${kube_context}" logs "${smoke_name}"; then
    kubectl --context "${kube_context}" describe pod "${smoke_name}" || true
    kubectl --context "${kube_context}" delete pod "${smoke_name}" --ignore-not-found --wait=false >/dev/null
    fail "Kubernetes GPU runtime smoke pod failed."
  fi

  kubectl --context "${kube_context}" delete pod "${smoke_name}" --ignore-not-found --wait=true >/dev/null
}

main() {
  log "$0 is running from: ${DIR}"

  [[ "$(uname -s)" == "Linux" ]] || fail "This installer is intended for Linux/WSL Ubuntu."

  require_cmd sudo
  require_cmd apt-get
  require_cmd docker

  mkdir -p "${LOCAL_BUCKETS_ROOT}"

  ensure_host_nested_gpu_handoff
  install_kind
  install_nvkind
  ensure_kind_registry

  if [[ "${CREATE_CLUSTER}" == "1" ]]; then
    create_kind_cluster
    connect_registry_to_kind_network
    publish_local_registry_config
    configure_kind_node_registry
    wait_for_kind_nodes_ready
    configure_kind_worker_nvidia_runtime
    wait_for_kind_nodes_ready
  fi

  if [[ "${INSTALL_DEVICE_PLUGIN}" == "1" ]]; then
    install_nvidia_device_plugin
  fi

  if [[ "${VERIFY_GPU_ALLOCATABLE}" == "1" ]]; then
    verify_gpu_allocatable
    verify_k8s_gpu_runtime
  fi

  cat <<EOF

Completed:
  - Docker/NVIDIA nested handoff configured for kind
  - kind installed
  - kind cluster target: ${KIND_CLUSTER_NAME}
  - node image: ${KIND_NODE_IMAGE}

Useful commands:
  kind get clusters
  kubectl config get-contexts
  kubectl --context kind-${KIND_CLUSTER_NAME} get nodes -o custom-columns=NAME:.metadata.name,GPU:.status.allocatable.nvidia\\.com/gpu

To load a locally built image into kind:
  kind load docker-image <image:tag> --name ${KIND_CLUSTER_NAME}

Local registry:
  push: localhost:${KIND_REGISTRY_HOST_PORT}
  pull from kind nodes: ${KIND_REGISTRY_CLUSTER_BINDING}

EOF
}

main "$@"
