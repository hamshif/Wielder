#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WIELDER_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REPO_ROOT="$(cd "${WIELDER_ROOT}/.." && pwd)"

source "${SCRIPT_DIR}/install_apt_helpers.sh"

WORKSPACE_PYTHON_VERSION="${WORKSPACE_PYTHON_VERSION:-3.11.11}"
WORKSPACE_VENV_PATH="${WORKSPACE_VENV_PATH:-${REPO_ROOT}/.venv}"
WORKSPACE_UVENV_NAME="${WORKSPACE_UVENV_NAME:-$(basename "${REPO_ROOT}")}"
RECREATE_VENV="${RECREATE_VENV:-0}"
WORKSPACE_LOCALE="${WORKSPACE_LOCALE:-en_US.UTF-8}"
UV_INSTALL_DIR="${UV_INSTALL_DIR:-${HOME}/.local/bin}"
UV_INSTALL_URL="${UV_INSTALL_URL:-https://astral.sh/uv/install.sh}"

JAVA_PACKAGE="${JAVA_PACKAGE:-openjdk-17-jdk}"
SPARK_VERSION="${SPARK_VERSION:-4.0.1}"
SPARK_DIST="${SPARK_DIST:-spark-${SPARK_VERSION}-bin-hadoop3}"
SPARK_ROOT="${SPARK_ROOT:-${HOME}/opt}"
SPARK_DOWNLOAD_URL="${SPARK_DOWNLOAD_URL:-https://archive.apache.org/dist/spark/spark-${SPARK_VERSION}/${SPARK_DIST}.tgz}"
SPARK_SHA512_URL="${SPARK_SHA512_URL:-${SPARK_DOWNLOAD_URL}.sha512}"
VERIFY_SPARK_SHA512="${VERIFY_SPARK_SHA512:-1}"
WORKSPACE_NODE_VERSION="${WORKSPACE_NODE_VERSION:-v22.19.0}"
WORKSPACE_NPM_VERSION="${WORKSPACE_NPM_VERSION:-11.6.1}"
WORKSPACE_NODE_ROOT="${WORKSPACE_NODE_ROOT:-${HOME}/opt}"
WORKSPACE_NODE_DIST="${WORKSPACE_NODE_DIST:-node-${WORKSPACE_NODE_VERSION}-linux-x64}"
WORKSPACE_NODE_HOME="${WORKSPACE_NODE_HOME:-${WORKSPACE_NODE_ROOT}/${WORKSPACE_NODE_DIST}}"
WORKSPACE_NODE_DOWNLOAD_URL="${WORKSPACE_NODE_DOWNLOAD_URL:-https://nodejs.org/dist/${WORKSPACE_NODE_VERSION}/${WORKSPACE_NODE_DIST}.tar.xz}"
WORKSPACE_NODE_SHASUMS_URL="${WORKSPACE_NODE_SHASUMS_URL:-https://nodejs.org/dist/${WORKSPACE_NODE_VERSION}/SHASUMS256.txt}"
VERIFY_NODE_SHA256="${VERIFY_NODE_SHA256:-1}"
TERRAFORM_VERSION="${TERRAFORM_VERSION:-latest}"
TERRAFORM_INSTALL_METHOD="${TERRAFORM_INSTALL_METHOD:-tfenv}"
TERRAFORM_APT_HOLD="${TERRAFORM_APT_HOLD:-0}"
TFENV_ROOT="${TFENV_ROOT:-${HOME}/.tfenv}"
TFENV_GIT_URL="${TFENV_GIT_URL:-https://github.com/tfutils/tfenv.git}"
OLLAMA_INSTALL_URL="${OLLAMA_INSTALL_URL:-https://ollama.com/install.sh}"

INSTALL_BASE="${INSTALL_BASE:-1}"
INSTALL_UV="${INSTALL_UV:-1}"
INSTALL_PYTHON_ENV="${INSTALL_PYTHON_ENV:-1}"
INSTALL_DIRECT_URL_REQUIREMENTS="${INSTALL_DIRECT_URL_REQUIREMENTS:-1}"
INSTALL_WORKSPACE_PACKAGES="${INSTALL_WORKSPACE_PACKAGES:-1}"
INSTALL_IDE_CONFIGS="${INSTALL_IDE_CONFIGS:-1}"
INSTALL_SHELL_CONFIG="${INSTALL_SHELL_CONFIG:-1}"
INSTALL_NODEJS="${INSTALL_NODEJS:-1}"
INSTALL_MODEL_ARTIFACT_TOOLS="${INSTALL_MODEL_ARTIFACT_TOOLS:-1}"
INSTALL_MODEL_LAUNCHER="${INSTALL_MODEL_LAUNCHER:-0}"
INSTALL_MODEL_SURFACE_DEPS="${INSTALL_MODEL_SURFACE_DEPS:-0}"
INSTALL_JAVA="${INSTALL_JAVA:-1}"
INSTALL_SPARK="${INSTALL_SPARK:-1}"
INSTALL_AWS_CLI="${INSTALL_AWS_CLI:-1}"
INSTALL_GITHUB_CLI="${INSTALL_GITHUB_CLI:-1}"
INSTALL_GCP_CLI="${INSTALL_GCP_CLI:-1}"
INSTALL_TERRAFORM="${INSTALL_TERRAFORM:-1}"
INSTALL_KUBERNETES_CLI="${INSTALL_KUBERNETES_CLI:-1}"
INSTALL_K9S="${INSTALL_K9S:-1}"
INSTALL_DESKTOP_APPS="${INSTALL_DESKTOP_APPS:-0}"
INSTALL_VSCODE_EXTENSIONS="${INSTALL_VSCODE_EXTENSIONS:-0}"
INSTALL_CUDA_TOOLKIT="${INSTALL_CUDA_TOOLKIT:-0}"
INSTALL_GPU_STACK="${INSTALL_GPU_STACK:-0}"
INSTALL_DOCKER="${INSTALL_DOCKER:-0}"
INSTALL_NVIDIA="${INSTALL_NVIDIA:-0}"
INSTALL_KIND="${INSTALL_KIND:-1}"
INSTALL_KIND_GPU="${INSTALL_KIND_GPU:-0}"
INSTALL_K3D="${INSTALL_K3D:-0}"
INSTALL_AZURE_CLI="${INSTALL_AZURE_CLI:-0}"
INSTALL_VISUALIZER="${INSTALL_VISUALIZER:-0}"
CUDA_TOOLKIT_PACKAGE="${CUDA_TOOLKIT_PACKAGE:-nvidia-cuda-toolkit}"
CUDA_HOST_GCC_PACKAGE="${CUDA_HOST_GCC_PACKAGE:-gcc-13}"
CUDA_HOST_GXX_PACKAGE="${CUDA_HOST_GXX_PACKAGE:-g++-13}"
CUDA_HOST_CC="${CUDA_HOST_CC:-/usr/bin/gcc-13}"
CUDA_HOST_CXX="${CUDA_HOST_CXX:-/usr/bin/g++-13}"
VSCODE_EXTENSIONS=(
  anthropic.claude-code
  ms-python.python
  ms-python.debugpy
  ms-python.vscode-pylance
  ms-python.vscode-python-envs
  ms-toolsai.jupyter
  ms-toolsai.jupyter-keymap
  ms-toolsai.jupyter-renderers
  ms-toolsai.vscode-jupyter-cell-tags
  ms-toolsai.vscode-jupyter-slideshow
  openai.chatgpt
  hashicorp.terraform
  redhat.vscode-yaml
  ms-azuretools.vscode-docker
  github.vscode-pull-request-github
)

RESTORE_WINDOWS_AWS_CONFIG="${RESTORE_WINDOWS_AWS_CONFIG:-0}"
AWS_CONFIG_RESTORE_ONLY="${AWS_CONFIG_RESTORE_ONLY:-0}"
OVERWRITE_AWS_CONFIG="${OVERWRITE_AWS_CONFIG:-0}"
WINDOWS_HOME="${WINDOWS_HOME:-}"

LIGHT_BLUE=$'\033[94m'
RESET_COLOR=$'\033[0m'
INSTALLED_ITEMS=()

BASE_APT_PACKAGES=(
  apt-transport-https
  bash-completion
  build-essential
  ca-certificates
  curl
  file
  g++
  gcc
  git
  gnupg
  groff
  jq
  less
  locales
  lsb-release
  make
  openssh-client
  pkg-config
  python-is-python3
  python3
  python3-venv
  rsync
  software-properties-common
  tar
  unzip
  util-linux-extra
  wget
  xz-utils
  zip
  zsh
)

GCP_CLI_APT_PACKAGES=(
  google-cloud-cli
)

KUBECTL_MINOR_VERSION="${KUBECTL_MINOR_VERSION:-v1.33}"
K9S_VERSION="${K9S_VERSION:-v0.50.18}"
K9S_INSTALL_DIR="${K9S_INSTALL_DIR:-/usr/local/bin}"
K9S_DOWNLOAD_BASE_URL="${K9S_DOWNLOAD_BASE_URL:-https://github.com/derailed/k9s/releases/download/${K9S_VERSION}}"
VERIFY_K9S_SHA256="${VERIFY_K9S_SHA256:-1}"

PYTHON_NATIVE_APT_PACKAGES=(
  libbz2-dev
  libffi-dev
  liblzma-dev
  libreadline-dev
  libsqlite3-dev
  libssl-dev
  zlib1g-dev
)

PYTHON_TOOL_REQUIREMENTS=(
  ipykernel
  jupyter
)

MODEL_ARTIFACT_PYTHON_REQUIREMENTS=(
  "huggingface_hub"
)

MODEL_ARTIFACT_APT_PACKAGES=(
  rclone
  zstd
)

WORKSPACE_PROJECTS=()
WORKSPACE_NO_DEPS_PROJECTS=()

DIRECT_URL_REQUIREMENTS=()
MODEL_LAUNCHER_PACKAGE_LOCK_GLOB="${MODEL_LAUNCHER_PACKAGE_LOCK_GLOB:-*/apps/model-launcher/package-lock.json}"
MODEL_SURFACE_DEPENDENCY_INSTALLERS_CSV="${MODEL_SURFACE_DEPENDENCY_INSTALLERS_CSV:-surface_dependancies/install_kalign.sh,surface_dependancies/install_hmmer.sh}"

PYTHON_ANALYSIS_PATHS=()

log() {
  printf '[install-ubuntu] %s\n' "$*"
}

fail() {
  printf '[install-ubuntu] ERROR: %s\n' "$*" >&2
  exit 1
}

run_step() {
  local name="$1"
  shift
  printf '\n[install-ubuntu] RUN %s\n' "${name}"
  "$@"
}

require_cmd() {
  local cmd="$1"
  command -v "$cmd" >/dev/null 2>&1 || fail "Required command not found: ${cmd}"
}

is_enabled() {
  [[ "${1}" == "1" || "${1}" == "true" || "${1}" == "yes" ]]
}

record_installed() {
  INSTALLED_ITEMS+=("$1")
}

install_phase_vars() {
  printf '%s\n' \
    INSTALL_BASE \
    INSTALL_UV \
    INSTALL_PYTHON_ENV \
    INSTALL_DIRECT_URL_REQUIREMENTS \
    INSTALL_WORKSPACE_PACKAGES \
    INSTALL_IDE_CONFIGS \
    INSTALL_SHELL_CONFIG \
    INSTALL_NODEJS \
    INSTALL_MODEL_ARTIFACT_TOOLS \
    INSTALL_MODEL_LAUNCHER \
    INSTALL_MODEL_SURFACE_DEPS \
    INSTALL_JAVA \
    INSTALL_SPARK \
    INSTALL_AWS_CLI \
    INSTALL_GITHUB_CLI \
    INSTALL_GCP_CLI \
    INSTALL_TERRAFORM \
    INSTALL_KUBERNETES_CLI \
    INSTALL_K9S \
    INSTALL_DESKTOP_APPS \
    INSTALL_VSCODE_EXTENSIONS \
    INSTALL_CUDA_TOOLKIT \
    INSTALL_GPU_STACK \
    INSTALL_DOCKER \
    INSTALL_NVIDIA \
    INSTALL_KIND \
    INSTALL_KIND_GPU \
    INSTALL_K3D \
    INSTALL_AZURE_CLI \
    INSTALL_VISUALIZER
}

disable_all_install_phases() {
  local phase_var
  while IFS= read -r phase_var; do
    printf -v "${phase_var}" '%s' "0"
  done < <(install_phase_vars)
}

enable_install_phase() {
  local phase_name="$1"
  case "${phase_name}" in
    base | apt | basics)
      INSTALL_BASE=1
      ;;
    uv)
      INSTALL_UV=1
      ;;
    python | python-env | venv)
      INSTALL_UV=1
      INSTALL_PYTHON_ENV=1
      ;;
    python-workspace | python-packages | workspace-python)
      INSTALL_UV=1
      INSTALL_PYTHON_ENV=1
      INSTALL_DIRECT_URL_REQUIREMENTS=1
      INSTALL_WORKSPACE_PACKAGES=1
      ;;
    direct-url | direct-url-requirements)
      INSTALL_DIRECT_URL_REQUIREMENTS=1
      ;;
    workspace | workspace-packages)
      INSTALL_WORKSPACE_PACKAGES=1
      ;;
    ide | ide-configs)
      INSTALL_IDE_CONFIGS=1
      ;;
    shell | shell-config)
      INSTALL_SHELL_CONFIG=1
      ;;
    node | nodejs | npm)
      INSTALL_NODEJS=1
      ;;
    model-artifacts | model-artifact-tools | models | rclone | ollama | huggingface | hf)
      INSTALL_UV=1
      INSTALL_PYTHON_ENV=1
      INSTALL_MODEL_ARTIFACT_TOOLS=1
      ;;
    model-launcher | model-web | launcher-web)
      INSTALL_NODEJS=1
      INSTALL_MODEL_LAUNCHER=1
      ;;
    model-surface-deps | model-host-deps | model-binaries)
      INSTALL_MODEL_SURFACE_DEPS=1
      ;;
    java)
      INSTALL_JAVA=1
      ;;
    spark)
      INSTALL_SPARK=1
      ;;
    aws | aws-cli)
      INSTALL_AWS_CLI=1
      ;;
    github | github-cli | gh)
      INSTALL_GITHUB_CLI=1
      ;;
    gcp | google-cloud | google-cloud-cli)
      INSTALL_GCP_CLI=1
      ;;
    desktop | desktop-apps)
      INSTALL_DESKTOP_APPS=1
      INSTALL_VSCODE_EXTENSIONS=1
      ;;
    vscode | vscode-extensions | code-extensions)
      INSTALL_VSCODE_EXTENSIONS=1
      ;;
    terraform)
      INSTALL_TERRAFORM=1
      ;;
    kubernetes | kubernetes-cli | k8s | kubectl | helm)
      INSTALL_KUBERNETES_CLI=1
      INSTALL_K9S=1
      ;;
    k9s)
      INSTALL_K9S=1
      ;;
    cuda | cuda-toolkit | host-cuda)
      INSTALL_CUDA_TOOLKIT=1
      ;;
    gpu | gpu-stack)
      INSTALL_CUDA_TOOLKIT=1
      INSTALL_GPU_STACK=1
      ;;
    docker)
      INSTALL_DOCKER=1
      ;;
    nvidia)
      INSTALL_NVIDIA=1
      ;;
    kind)
      INSTALL_KIND=1
      ;;
    kind-gpu)
      INSTALL_KIND_GPU=1
      ;;
    k3d)
      INSTALL_K3D=1
      ;;
    azure | azure-cli)
      INSTALL_AZURE_CLI=1
      ;;
    visualizer)
      INSTALL_VISUALIZER=1
      ;;
    *)
      fail "Unknown install phase: ${phase_name}"
      ;;
  esac
}

disable_install_phase() {
  local phase_name="$1"
  case "${phase_name}" in
    base | apt | basics)
      INSTALL_BASE=0
      ;;
    uv)
      INSTALL_UV=0
      ;;
    python | python-env | venv)
      INSTALL_PYTHON_ENV=0
      ;;
    direct-url | direct-url-requirements)
      INSTALL_DIRECT_URL_REQUIREMENTS=0
      ;;
    workspace | workspace-packages)
      INSTALL_WORKSPACE_PACKAGES=0
      ;;
    ide | ide-configs)
      INSTALL_IDE_CONFIGS=0
      ;;
    shell | shell-config)
      INSTALL_SHELL_CONFIG=0
      ;;
    node | nodejs | npm)
      INSTALL_NODEJS=0
      ;;
    model-artifacts | model-artifact-tools | models | rclone | ollama | huggingface | hf)
      INSTALL_MODEL_ARTIFACT_TOOLS=0
      ;;
    model-launcher | model-web | launcher-web)
      INSTALL_MODEL_LAUNCHER=0
      ;;
    model-surface-deps | model-host-deps | model-binaries)
      INSTALL_MODEL_SURFACE_DEPS=0
      ;;
    java)
      INSTALL_JAVA=0
      ;;
    spark)
      INSTALL_SPARK=0
      ;;
    aws | aws-cli)
      INSTALL_AWS_CLI=0
      ;;
    github | github-cli | gh)
      INSTALL_GITHUB_CLI=0
      ;;
    gcp | google-cloud | google-cloud-cli)
      INSTALL_GCP_CLI=0
      ;;
    desktop | desktop-apps)
      INSTALL_DESKTOP_APPS=0
      INSTALL_VSCODE_EXTENSIONS=0
      ;;
    vscode | vscode-extensions | code-extensions)
      INSTALL_VSCODE_EXTENSIONS=0
      ;;
    terraform)
      INSTALL_TERRAFORM=0
      ;;
    kubernetes | kubernetes-cli | k8s | kubectl | helm)
      INSTALL_KUBERNETES_CLI=0
      INSTALL_K9S=0
      ;;
    k9s)
      INSTALL_K9S=0
      ;;
    cuda | cuda-toolkit | host-cuda)
      INSTALL_CUDA_TOOLKIT=0
      ;;
    gpu | gpu-stack)
      INSTALL_GPU_STACK=0
      ;;
    docker)
      INSTALL_DOCKER=0
      ;;
    nvidia)
      INSTALL_NVIDIA=0
      ;;
    kind)
      INSTALL_KIND=0
      ;;
    kind-gpu)
      INSTALL_KIND_GPU=0
      ;;
    k3d)
      INSTALL_K3D=0
      ;;
    azure | azure-cli)
      INSTALL_AZURE_CLI=0
      ;;
    visualizer)
      INSTALL_VISUALIZER=0
      ;;
    *)
      fail "Unknown install phase: ${phase_name}"
      ;;
  esac
}

print_usage() {
  cat <<EOF
Usage:
  ${SCRIPT_DIR}/install_ubuntu.sh
  ${SCRIPT_DIR}/install_ubuntu.sh --with docker
  ${SCRIPT_DIR}/install_ubuntu.sh --only kubernetes-cli
  ${SCRIPT_DIR}/install_ubuntu.sh --skip workspace-packages --skip spark

Common phase names:
  base uv python-env direct-url-requirements workspace-packages ide-configs shell-config
  nodejs model-artifact-tools model-launcher model-surface-deps java spark aws-cli github-cli google-cloud-cli terraform kubernetes-cli k9s desktop-apps vscode-extensions
  cuda-toolkit docker nvidia gpu-stack kind kind-gpu k3d azure-cli visualizer

Environment variables remain supported for automation, but operator handoffs should prefer arguments.
EOF
}

parse_args() {
  while (($#)); do
    case "$1" in
      --help | -h)
        print_usage
        exit 0
        ;;
      --only)
        shift
        [[ $# -gt 0 ]] || fail "--only requires at least one phase name."
        disable_all_install_phases
        while (($#)); do
          [[ "$1" == --* ]] && break
          enable_install_phase "$1"
          shift
        done
        ;;
      --with)
        shift
        [[ $# -gt 0 ]] || fail "--with requires at least one phase name."
        while (($#)); do
          [[ "$1" == --* ]] && break
          enable_install_phase "$1"
          shift
        done
        ;;
      --with=*)
        enable_install_phase "${1#--with=}"
        shift
        ;;
      --only=*)
        disable_all_install_phases
        enable_install_phase "${1#--only=}"
        shift
        ;;
      --skip)
        shift
        [[ $# -gt 0 ]] || fail "--skip requires a phase name."
        disable_install_phase "$1"
        shift
        ;;
      --skip=*)
        disable_install_phase "${1#--skip=}"
        shift
        ;;
      *)
        fail "Unknown argument: $1"
        ;;
    esac
  done
}

array_contains() {
  local needle="$1"
  shift
  local item
  for item in "$@"; do
    [[ "${item}" == "${needle}" ]] && return 0
  done
  return 1
}

append_unique() {
  local array_name="$1"
  local value="$2"
  eval "local existing=(\"\${${array_name}[@]}\")"
  if ! array_contains "${value}" "${existing[@]}"; then
    eval "${array_name}+=(\"\${value}\")"
  fi
}

load_csv_array() {
  local array_name="$1"
  local csv="$2"
  local item
  local -a _csv_items
  IFS=',' read -r -a _csv_items <<<"${csv}"
  for item in "${_csv_items[@]}"; do
    item="${item#"${item%%[![:space:]]*}"}"
    item="${item%"${item##*[![:space:]]}"}"
    [[ -n "${item}" ]] && append_unique "${array_name}" "${item}"
  done
}

git_submodule_paths() {
  if [[ -f "${REPO_ROOT}/.gitmodules" ]]; then
    git -C "${REPO_ROOT}" config --file .gitmodules --get-regexp path 2>/dev/null | awk '{ print $2 }'
  fi
}

populate_workspace_project_defaults() {
  local project src_path

  if [[ ${#WORKSPACE_PROJECTS[@]} -eq 0 && -n "${WORKSPACE_PROJECTS_CSV:-}" ]]; then
    load_csv_array WORKSPACE_PROJECTS "${WORKSPACE_PROJECTS_CSV}"
  fi
  if [[ ${#WORKSPACE_NO_DEPS_PROJECTS[@]} -eq 0 && -n "${WORKSPACE_NO_DEPS_PROJECTS_CSV:-}" ]]; then
    load_csv_array WORKSPACE_NO_DEPS_PROJECTS "${WORKSPACE_NO_DEPS_PROJECTS_CSV}"
  fi
  if [[ ${#PYTHON_ANALYSIS_PATHS[@]} -eq 0 && -n "${PYTHON_ANALYSIS_PATHS_CSV:-}" ]]; then
    load_csv_array PYTHON_ANALYSIS_PATHS "${PYTHON_ANALYSIS_PATHS_CSV}"
  fi

  append_unique WORKSPACE_PROJECTS "Wielder"
  while IFS= read -r project; do
    [[ -z "${project}" ]] && continue
    if [[ -f "${REPO_ROOT}/${project}/pyproject.toml" || -f "${REPO_ROOT}/${project}/setup.py" ]]; then
      append_unique WORKSPACE_PROJECTS "${project}"
    fi
  done < <(git_submodule_paths)

  for project in "${WORKSPACE_PROJECTS[@]}"; do
    if [[ -d "${REPO_ROOT}/${project}/src" ]]; then
      append_unique PYTHON_ANALYSIS_PATHS "./${project}/src"
    elif [[ -d "${REPO_ROOT}/${project}" ]]; then
      append_unique PYTHON_ANALYSIS_PATHS "./${project}"
    fi
  done
}

ensure_ubuntu() {
  [[ "$(uname -s)" == "Linux" ]] || fail "This installer is intended for Ubuntu Linux/WSL."
  [[ -f /etc/os-release ]] || fail "Missing /etc/os-release."

  # shellcheck disable=SC1091
  source /etc/os-release
  if [[ "${ID:-}" != "ubuntu" && "${ALLOW_NON_UBUNTU:-0}" != "1" ]]; then
    fail "Expected Ubuntu, found [${PRETTY_NAME:-unknown}]. Set ALLOW_NON_UBUNTU=1 to continue anyway."
  fi

  require_cmd sudo
  require_cmd apt-get
}

ensure_base_packages() {
  apt_get_safe update
  apt_get_safe install -y "${BASE_APT_PACKAGES[@]}" "${PYTHON_NATIVE_APT_PACKAGES[@]}"
  if command -v locale-gen >/dev/null 2>&1; then
    sudo locale-gen "${WORKSPACE_LOCALE}" >/dev/null
    sudo update-locale "LANG=${WORKSPACE_LOCALE}" >/dev/null || true
  fi
  record_installed "Ubuntu base packages: ${BASE_APT_PACKAGES[*]}"
  record_installed "Python native build headers: ${PYTHON_NATIVE_APT_PACKAGES[*]}"
  record_installed "Locale: ${WORKSPACE_LOCALE}"
}

ensure_uv() {
  mkdir -p "${UV_INSTALL_DIR}"
  export PATH="${UV_INSTALL_DIR}:${PATH}"

  if command -v uv >/dev/null 2>&1; then
    log "uv already available: $(uv --version)"
    if uv self update >/dev/null 2>&1; then
      log "uv updated: $(uv --version)"
    else
      log "uv self update is not available for this uv installation; continuing with existing uv."
    fi
    record_installed "uv: $(uv --version)"
    return
  fi

  require_cmd curl
  log "Installing uv into ${UV_INSTALL_DIR}."
  curl -LsSf "${UV_INSTALL_URL}" | env UV_UNMANAGED_INSTALL="${UV_INSTALL_DIR}" sh
  export PATH="${UV_INSTALL_DIR}:${PATH}"
  require_cmd uv
  log "uv installed: $(uv --version)"
  record_installed "uv: $(uv --version)"
}

venv_python() {
  printf '%s/bin/python\n' "${WORKSPACE_VENV_PATH}"
}

require_venv_python() {
  local phase_name="$1"
  local python_bin
  python_bin="$(venv_python)"

  [[ -x "${python_bin}" ]] && {
    printf '%s\n' "${python_bin}"
    return
  }

  fail "${phase_name} requires the workspace virtual environment at ${WORKSPACE_VENV_PATH}.
Create it first with:
  ${SCRIPT_DIR}/install_ubuntu.sh --only python-env
Or create the venv and install workspace packages together with:
  ${SCRIPT_DIR}/install_ubuntu.sh --only python-workspace"
}

venv_python_version() {
  local python_bin="$1"
  [[ -x "${python_bin}" ]] || return 1
  "${python_bin}" -c 'import platform; print(platform.python_version())'
}

ensure_venv() {
  local python_bin existing_version
  python_bin="$(venv_python)"

  if [[ -x "${python_bin}" ]]; then
    existing_version="$(venv_python_version "${python_bin}" 2>/dev/null || true)"
    if [[ "${existing_version}" == "${WORKSPACE_PYTHON_VERSION}" ]]; then
      if ! is_enabled "${RECREATE_VENV}" && ! is_enabled "${UV_VENV_CLEAR:-0}"; then
        log "Reusing existing virtual environment at ${WORKSPACE_VENV_PATH} with Python ${existing_version}."
        return
      fi
    fi

    if is_enabled "${RECREATE_VENV}" || is_enabled "${UV_VENV_CLEAR:-0}"; then
      log "Recreating virtual environment at ${WORKSPACE_VENV_PATH}."
      uv venv --clear --python "${WORKSPACE_PYTHON_VERSION}" "${WORKSPACE_VENV_PATH}"
      return
    fi

    fail "Virtual environment at ${WORKSPACE_VENV_PATH} uses Python [${existing_version:-unknown}], expected [${WORKSPACE_PYTHON_VERSION}].
Set RECREATE_VENV=1 to replace it."
  fi

  log "Creating virtual environment at ${WORKSPACE_VENV_PATH}."
  uv venv --python "${WORKSPACE_PYTHON_VERSION}" "${WORKSPACE_VENV_PATH}"
}

ensure_python_env() {
  export PATH="${UV_INSTALL_DIR}:${PATH}"
  require_cmd uv

  log "Ensuring Python ${WORKSPACE_PYTHON_VERSION} through uv."
  uv python install "${WORKSPACE_PYTHON_VERSION}"

  log "Ensuring virtual environment at ${WORKSPACE_VENV_PATH}."
  ensure_venv

  local python_bin
  python_bin="$(venv_python)"
  [[ -x "${python_bin}" ]] || fail "Expected venv Python not found: ${python_bin}"

  printf '%s\n' "${WORKSPACE_PYTHON_VERSION}" > "${REPO_ROOT}/.python-version"
  uv pip install --python "${python_bin}" --upgrade pip setuptools wheel "${PYTHON_TOOL_REQUIREMENTS[@]}"
  record_installed "Python ${WORKSPACE_PYTHON_VERSION} virtual environment: ${WORKSPACE_VENV_PATH}"
  record_installed "Python packaging tools: pip setuptools wheel"
  record_installed "Notebook kernel tools: ${PYTHON_TOOL_REQUIREMENTS[*]}"
}

ensure_direct_url_requirements() {
  export PATH="${UV_INSTALL_DIR}:${PATH}"
  require_cmd uv

  local python_bin requirement
  python_bin="$(require_venv_python "Direct URL requirements")"

  if [[ ${#DIRECT_URL_REQUIREMENTS[@]} -eq 0 && -n "${DIRECT_URL_REQUIREMENTS_CSV:-}" ]]; then
    load_csv_array DIRECT_URL_REQUIREMENTS "${DIRECT_URL_REQUIREMENTS_CSV}"
  fi

  if [[ ${#DIRECT_URL_REQUIREMENTS[@]} -eq 0 ]]; then
    log "No direct URL Python requirements configured."
    return
  fi

  for requirement in "${DIRECT_URL_REQUIREMENTS[@]}"; do
    log "Installing direct URL requirement: ${requirement}"
    uv pip install --python "${python_bin}" "${requirement}"
    record_installed "Direct URL Python requirement: ${requirement}"
  done
}

install_editable_project() {
  local project_name="$1"
  local project_dir="${REPO_ROOT}/${project_name}"
  local python_bin
  python_bin="$(require_venv_python "Workspace package installation")"

  [[ -d "${project_dir}" ]] || {
    log "Skipping missing project: ${project_dir}"
    return
  }

  if [[ ! -f "${project_dir}/pyproject.toml" && ! -f "${project_dir}/setup.py" ]]; then
    log "Skipping non-Python project without pyproject.toml/setup.py: ${project_dir}"
    return
  fi

  log "Installing editable project: ${project_name}"
  if array_contains "${project_name}" "${WORKSPACE_NO_DEPS_PROJECTS[@]}"; then
    log "Installing ${project_name} without dependency re-resolution; workspace dependencies were installed earlier."
    uv pip install --python "${python_bin}" --no-deps -e "${project_dir}"
  else
    uv pip install --python "${python_bin}" -e "${project_dir}"
  fi
  record_installed "Editable Python project: ${project_name}"
}

ensure_workspace_packages() {
  export PATH="${UV_INSTALL_DIR}:${PATH}"
  require_cmd uv
  populate_workspace_project_defaults

  local project
  for project in "${WORKSPACE_PROJECTS[@]}"; do
    install_editable_project "${project}"
  done
}

render_ide_configs() {
  local python_bin
  local vscode_extensions_json
  populate_workspace_project_defaults
  python_bin="$(venv_python)"
  [[ -x "${python_bin}" ]] || fail "Cannot render IDE configs before venv exists: ${python_bin}"

  mkdir -p "${REPO_ROOT}/.vscode"
  printf '%s\n' "${WORKSPACE_PYTHON_VERSION}" > "${REPO_ROOT}/.python-version"

  vscode_extensions_json="$(
    printf '%s\n' "${VSCODE_EXTENSIONS[@]}" | "${python_bin}" -c 'import json, sys; print(json.dumps([line.strip() for line in sys.stdin if line.strip()]))'
  )"

  WORKSPACE_VSCODE_EXTENSIONS_JSON="${vscode_extensions_json}" \
    "${python_bin}" - "${REPO_ROOT}" "${WORKSPACE_VENV_PATH}" "${WORKSPACE_PYTHON_VERSION}" "${PYTHON_ANALYSIS_PATHS[@]}" <<'PY'
import json
import os
import sys
from pathlib import Path

repo_root = Path(sys.argv[1])
venv_path = Path(sys.argv[2])
python_version = sys.argv[3]
analysis_paths = list(sys.argv[4:])
default_extensions = json.loads(os.environ.get("WORKSPACE_VSCODE_EXTENSIONS_JSON", "[]"))

settings_path = repo_root / ".vscode" / "settings.json"
extensions_path = repo_root / ".vscode" / "extensions.json"
pyright_path = repo_root / "pyrightconfig.json"

settings = {}
if settings_path.exists():
    try:
        settings = json.loads(settings_path.read_text())
    except json.JSONDecodeError:
        settings = {}

settings.update(
    {
        "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
        "python.pythonPath": "${workspaceFolder}/.venv/bin/python",
        "python.terminal.activateEnvironment": True,
        "python.testing.pytestEnabled": True,
        "python.testing.unittestEnabled": False,
        "python.testing.nosetestsEnabled": False,
        "python.testing.pytestArgs": settings.get("python.testing.pytestArgs", ["."]),
        "python.analysis.extraPaths": analysis_paths,
        "python.autoComplete.extraPaths": analysis_paths,
    }
)
settings_path.write_text(json.dumps(settings, indent=4, sort_keys=True) + "\n")

extensions = {}
if extensions_path.exists():
    try:
        extensions = json.loads(extensions_path.read_text())
    except json.JSONDecodeError:
        extensions = {}
recommendations = list(extensions.get("recommendations", []))
for extension_id in default_extensions:
    if extension_id not in recommendations:
        recommendations.append(extension_id)
extensions["recommendations"] = recommendations
extensions_path.write_text(json.dumps(extensions, indent=4, sort_keys=True) + "\n")

pyright = {}
if pyright_path.exists():
    try:
        pyright = json.loads(pyright_path.read_text())
    except json.JSONDecodeError:
        pyright = {}
elif (repo_root / "pyrightconfig.json.example").exists():
    try:
        pyright = json.loads((repo_root / "pyrightconfig.json.example").read_text())
    except json.JSONDecodeError:
        pyright = {}

pyright.update(
    {
        "venvPath": ".",
        "venv": ".venv",
        "pythonVersion": python_version,
        "extraPaths": analysis_paths,
        "executionEnvironments": pyright.get("executionEnvironments", [{"root": "./"}]),
    }
)
pyright_path.write_text(json.dumps(pyright, indent=4, sort_keys=True) + "\n")

print(f"Rendered VS Code settings: {settings_path}")
print(f"Rendered VS Code extension recommendations: {extensions_path}")
print(f"Rendered Pyright config: {pyright_path}")
print(f"Interpreter: {venv_path / 'bin' / 'python'}")
PY

  record_installed "VS Code settings: ${REPO_ROOT}/.vscode/settings.json"
  record_installed "VS Code extension recommendations: ${REPO_ROOT}/.vscode/extensions.json"
  record_installed "Pyright config: ${REPO_ROOT}/pyrightconfig.json"
}

render_shell_config() {
  local python_bin
  python_bin="$(venv_python)"
  if [[ ! -x "${python_bin}" ]]; then
    if command -v python3 >/dev/null 2>&1; then
      python_bin="$(command -v python3)"
    elif command -v python >/dev/null 2>&1; then
      python_bin="$(command -v python)"
    else
      fail "Cannot render shell config before venv exists and no system python is on PATH: $(venv_python)"
    fi
    log "Rendering shell config with ${python_bin}; ${WORKSPACE_VENV_PATH} can be created later with --only python-env."
  fi

  "${python_bin}" - "${HOME}/.zshrc" "${HOME}/.bashrc" "${REPO_ROOT}" "${WORKSPACE_VENV_PATH}" "${WORKSPACE_UVENV_NAME}" "${SPARK_ROOT}/spark-4" "${WORKSPACE_LOCALE}" "${WORKSPACE_PYTHON_VERSION}" "${WORKSPACE_NODE_HOME}" <<'PY'
import sys
from pathlib import Path

zshrc_path = Path(sys.argv[1])
bashrc_path = Path(sys.argv[2])
repo_root = Path(sys.argv[3])
venv_path = Path(sys.argv[4])
uvenv_name = sys.argv[5]
spark_alias = Path(sys.argv[6])
locale_name = sys.argv[7]
python_version = sys.argv[8]
node_home = Path(sys.argv[9])
uvenv_helper = repo_root / "Wielder" / "wielder" / "scripts" / "uvenv.sh"

def replace_managed_block(path: Path, block: str) -> None:
    start = "# >>> workspace managed >>>"
    end = "# <<< workspace managed <<<"
    text = path.read_text() if path.exists() else ""
    if start in text and end in text:
        before, rest = text.split(start, 1)
        _, after = rest.split(end, 1)
        text = before.rstrip() + "\n\n" + block + after.lstrip("\n")
    else:
        text = text.rstrip() + "\n\n" + block
    path.write_text(text)

common_block = f"""# >>> workspace managed >>>
# Workspace local tooling. Keep this minimal; the maintained installer owns setup:
#   {repo_root}/Wielder/wielder/scripts/install_ubuntu.sh
export WORKSPACE_ROOT="{repo_root}"
export WORKSPACE_DEFAULT_VENV="{venv_path}"
export UVENV_DEFAULT_VENV="${{UVENV_DEFAULT_VENV:-{venv_path}}}"
export UVENV_DEFAULT_NAME="${{UVENV_DEFAULT_NAME:-{uvenv_name}}}"
export UVENV_PYTHON_VERSION="{python_version}"
export UVENV_HOME="${{UVENV_HOME:-$HOME/.uvenvs}}"
export VIRTUAL_ENV_DISABLE_PROMPT=1

_workspace_prepend_path() {{
  case ":$PATH:" in
    *":$1:"*) ;;
    *) export PATH="$1:$PATH" ;;
  esac
}}

if [[ -f "{uvenv_helper}" ]]; then
  # shellcheck disable=SC1091
  source "{uvenv_helper}"
fi

workspace-activate() {{
  uvenv activate "$WORKSPACE_DEFAULT_VENV"
}}

workspace-deactivate() {{
  uvenv deactivate
}}

_workspace_prepend_path "$HOME/.local/bin"
export TFENV_ROOT="$HOME/.tfenv"
_workspace_prepend_path "$TFENV_ROOT/bin"

export WORKSPACE_NODE_HOME="{node_home}"
_workspace_prepend_path "$WORKSPACE_NODE_HOME/bin"

export SPARK4_HOME="{spark_alias}"
export SPARK_HOME="$SPARK4_HOME"
export PYSPARK_HOME="$SPARK4_HOME"
export PYSPARK_PYTHON="{venv_path}/bin/python"
_workspace_prepend_path "$SPARK_HOME/bin"

if typeset -f uvenv >/dev/null 2>&1; then
  uvenv activate "$UVENV_DEFAULT_VENV" >/dev/null 2>&1 || true
fi

if [[ -f /etc/profile.d/wielder-cuda.sh ]]; then
  source /etc/profile.d/wielder-cuda.sh
fi

alias workspace='cd "$WORKSPACE_ROOT"'
alias workspace-python="$WORKSPACE_DEFAULT_VENV/bin/python"

export EDITOR="${{EDITOR:-nano}}"
export LANG="${{LANG:-{locale_name}}}"
export LC_CTYPE="${{LC_CTYPE:-{locale_name}}}"
unset LC_ALL
"""

zsh_block = common_block + f"""
if command -v uv >/dev/null 2>&1; then
  eval "$(uv generate-shell-completion zsh 2>/dev/null || true)"
fi

if command -v kubectl >/dev/null 2>&1; then
  source <(kubectl completion zsh)
fi

if command -v helm >/dev/null 2>&1; then
  source <(helm completion zsh)
fi

if command -v k9s >/dev/null 2>&1; then
  source <(k9s completion zsh 2>/dev/null || true)
fi

autoload -Uz colors vcs_info add-zsh-hook
colors
zstyle ':vcs_info:git:*' formats ' git:(%F{{red}}%b%f)'

__workspace_vcs_info_precmd() {{
  vcs_info
}}

if (( ${{+functions[add-zsh-hook]}} )); then
  add-zsh-hook -d precmd __workspace_vcs_info_precmd 2>/dev/null || true
  add-zsh-hook precmd __workspace_vcs_info_precmd
else
  precmd_functions=(${{precmd_functions:#__workspace_vcs_info_precmd}} __workspace_vcs_info_precmd)
fi

__uvenv_venv_prompt() {{
  local label="${{UVENV_ACTIVE_NAME:-}}"
  if [[ -z "$label" && -n "${{VIRTUAL_ENV_PROMPT:-}}" ]]; then
    label="${{VIRTUAL_ENV_PROMPT}}"
    label="${{label#(}}"
    label="${{label%) }}"
    label="${{label%)}}"
  fi
  if [[ -z "$label" && -n "${{VIRTUAL_ENV:-}}" ]]; then
    label="${{VIRTUAL_ENV##*/}}"
  fi
  [[ -n "$label" ]] && printf '(%s) ' "$label"
}}

setopt prompt_subst
PROMPT='$(__uvenv_venv_prompt)%F{{green}}➜%f  %F{{cyan}}%1~%f${{vcs_info_msg_0_}} '

if [[ -f "$HOME/.zsh_secrets" ]]; then
  source "$HOME/.zsh_secrets"
fi

unset -f _workspace_prepend_path 2>/dev/null || true
# <<< workspace managed <<<
"""

bash_block = common_block + """
if [[ -f /etc/bash_completion ]]; then
  # shellcheck disable=SC1091
  source /etc/bash_completion
fi

if command -v uv >/dev/null 2>&1; then
  eval "$(uv generate-shell-completion bash 2>/dev/null || true)"
fi

if command -v kubectl >/dev/null 2>&1; then
  source <(kubectl completion bash)
fi

if command -v helm >/dev/null 2>&1; then
  source <(helm completion bash)
fi

if command -v k9s >/dev/null 2>&1; then
  source <(k9s completion bash 2>/dev/null || true)
fi

__workspace_git_branch() {
  git branch --show-current 2>/dev/null
}

__workspace_prompt() {
  local branch=""
  local git_prompt=""
  branch="$(__workspace_git_branch)"
  if [[ -n "$branch" ]]; then
    git_prompt=" git:($branch)"
  fi
  PS1="\\[\\033[32m\\]➜\\[\\033[0m\\]  \\[\\033[36m\\]\\W\\[\\033[0m\\]${git_prompt} "
}

case ";${PROMPT_COMMAND:-};" in
  *";__workspace_prompt;"*) ;;
  *) PROMPT_COMMAND="__workspace_prompt${PROMPT_COMMAND:+;$PROMPT_COMMAND}" ;;
esac

if [[ -f "$HOME/.bash_secrets" ]]; then
  source "$HOME/.bash_secrets"
elif [[ -f "$HOME/.zsh_secrets" ]]; then
  source "$HOME/.zsh_secrets"
fi

unset -f _workspace_prepend_path 2>/dev/null || true
# <<< workspace managed <<<
"""

replace_managed_block(zshrc_path, zsh_block)
replace_managed_block(bashrc_path, bash_block)
PY

  record_installed "Shell config: ${HOME}/.zshrc"
  record_installed "Shell config: ${HOME}/.bashrc"
}

ensure_tfenv_shell_config() {
  local rc_path
  local tfenv_path_line='export PATH="$TFENV_ROOT/bin:$PATH"'

  for rc_path in "${HOME}/.zshrc" "${HOME}/.bashrc"; do
    if [[ -f "${rc_path}" ]] && grep -Fq "${tfenv_path_line}" "${rc_path}"; then
      log "Shell config already includes tfenv PATH: ${rc_path}"
      continue
    fi

    touch "${rc_path}"
    cat >> "${rc_path}" <<'EOF'

# >>> workspace tfenv >>>
export TFENV_ROOT="$HOME/.tfenv"
export PATH="$TFENV_ROOT/bin:$PATH"
# <<< workspace tfenv <<<
EOF
    record_installed "Shell config tfenv PATH: ${rc_path}"
  done
}

ensure_nodejs() {
  require_cmd curl
  require_cmd tar

  [[ -n "${WORKSPACE_NODE_DIST}" && "${WORKSPACE_NODE_DIST}" != */* ]] || fail "WORKSPACE_NODE_DIST must be a distribution directory name, not a path."
  [[ -n "${WORKSPACE_NODE_ROOT}" && "${WORKSPACE_NODE_ROOT}" != "/" ]] || fail "WORKSPACE_NODE_ROOT must not be empty or /."

  local node_bin npm_bin installed_node_version installed_npm_version
  node_bin="${WORKSPACE_NODE_HOME}/bin/node"
  npm_bin="${WORKSPACE_NODE_HOME}/bin/npm"

  if [[ -x "${node_bin}" ]] && [[ "$("${node_bin}" --version)" == "${WORKSPACE_NODE_VERSION}" ]]; then
    log "Node.js ${WORKSPACE_NODE_VERSION} already available at ${WORKSPACE_NODE_HOME}."
  else
    local tmp_dir archive_path
    tmp_dir="$(mktemp -d)"
    archive_path="${tmp_dir}/${WORKSPACE_NODE_DIST}.tar.xz"

    log "Downloading Node.js ${WORKSPACE_NODE_VERSION} from ${WORKSPACE_NODE_DOWNLOAD_URL}."
    if ! (
      set -euo pipefail
      cd "${tmp_dir}"
      curl -fL "${WORKSPACE_NODE_DOWNLOAD_URL}" -o "${archive_path}"
      if is_enabled "${VERIFY_NODE_SHA256}"; then
        log "Verifying Node.js archive checksum."
        curl -fL "${WORKSPACE_NODE_SHASUMS_URL}" -o SHASUMS256.txt
        grep -F " ${WORKSPACE_NODE_DIST}.tar.xz" SHASUMS256.txt | sha256sum -c -
      fi
      mkdir -p "${WORKSPACE_NODE_ROOT}"
      rm -rf "${WORKSPACE_NODE_HOME}"
      tar -xJf "${archive_path}" -C "${WORKSPACE_NODE_ROOT}"
    ); then
      rm -rf "${tmp_dir}"
      return 1
    fi
    rm -rf "${tmp_dir}"
  fi

  [[ -x "${node_bin}" ]] || fail "Expected Node.js executable not found: ${node_bin}"
  [[ -x "${npm_bin}" ]] || fail "Expected npm executable not found: ${npm_bin}"

  export PATH="${WORKSPACE_NODE_HOME}/bin:${PATH}"
  installed_node_version="$("${node_bin}" --version)"
  if [[ "${installed_node_version}" != "${WORKSPACE_NODE_VERSION}" ]]; then
    fail "Node.js at ${WORKSPACE_NODE_HOME} is ${installed_node_version}, expected ${WORKSPACE_NODE_VERSION}."
  fi

  if ! "${npm_bin}" --version | grep -Eq '^(11\.|1[2-9]\.)'; then
    log "Upgrading npm to ${WORKSPACE_NPM_VERSION}."
    "${npm_bin}" install -g "npm@${WORKSPACE_NPM_VERSION}" >/dev/null
  fi
  installed_npm_version="$("${npm_bin}" --version)"

  log "Node.js available: ${installed_node_version}; npm ${installed_npm_version}"
  record_installed "Node.js: ${WORKSPACE_NODE_HOME} (${installed_node_version}, npm ${installed_npm_version})"
}

ensure_model_artifact_tools() {
  local python_bin requirement
  python_bin="$(require_venv_python "Model artifact tools")"

  if command -v rclone >/dev/null 2>&1 && command -v zstd >/dev/null 2>&1; then
    log "rclone already available: $(rclone version | sed -n '1p')"
    log "zstd already available: $(zstd --version | sed -n '1p')"
  else
    apt_get_safe update
    apt_get_safe install -y "${MODEL_ARTIFACT_APT_PACKAGES[@]}"
    require_cmd rclone
    require_cmd zstd
  fi

  export PATH="${UV_INSTALL_DIR}:${PATH}"
  require_cmd uv
  for requirement in "${MODEL_ARTIFACT_PYTHON_REQUIREMENTS[@]}"; do
    log "Installing model artifact Python requirement: ${requirement}"
    uv pip install --python "${python_bin}" "${requirement}"
  done

  if command -v ollama >/dev/null 2>&1; then
    log "Ollama already available: $(ollama --version 2>&1 | sed -n '1p')"
  else
    require_cmd curl
    require_cmd zstd
    log "Installing Ollama from ${OLLAMA_INSTALL_URL}."
    curl -fsSL "${OLLAMA_INSTALL_URL}" | sh
    require_cmd ollama
  fi

  record_installed "rclone: $(rclone version | sed -n '1p')"
  record_installed "zstd: $(zstd --version | sed -n '1p')"
  record_installed "Hugging Face CLI Python package: ${MODEL_ARTIFACT_PYTHON_REQUIREMENTS[*]}"
  record_installed "Ollama: $(ollama --version 2>&1 | sed -n '1p')"
}

ensure_model_launcher_web_deps() {
  local launcher_dir npm_bin
  launcher_dir="$(find "${REPO_ROOT}" -path "${MODEL_LAUNCHER_PACKAGE_LOCK_GLOB}" -print -quit | xargs -r dirname)"
  npm_bin="${WORKSPACE_NODE_HOME}/bin/npm"

  [[ -n "${launcher_dir}" && -d "${launcher_dir}" ]] || fail "Model launcher directory matching [${MODEL_LAUNCHER_PACKAGE_LOCK_GLOB}] not found under ${REPO_ROOT}"
  [[ -f "${launcher_dir}/package-lock.json" ]] || fail "Model launcher package-lock.json not found: ${launcher_dir}/package-lock.json"
  [[ -x "${npm_bin}" ]] || fail "npm was not found at ${npm_bin}. Run ${SCRIPT_DIR}/install_ubuntu.sh --only nodejs first."

  export PATH="${WORKSPACE_NODE_HOME}/bin:${PATH}"
  log "Installing model launcher web dependencies with npm ci."
  (cd "${launcher_dir}" && npm ci)
  record_installed "Model launcher web dependencies: ${launcher_dir}/node_modules"
}

ensure_model_surface_deps() {
  local installer relative_installer
  local -a installer_paths=()
  load_csv_array installer_paths "${MODEL_SURFACE_DEPENDENCY_INSTALLERS_CSV}"

  for relative_installer in "${installer_paths[@]}"; do
    installer="$(find "${REPO_ROOT}" -path "*/${relative_installer}" -print -quit)"
    [[ -x "${installer}" ]] || fail "Missing executable model surface dependency installer for [${relative_installer}]: ${installer}"
    "${installer}"
  done

  command -v kalign >/dev/null 2>&1 && record_installed "Model surface dependency: kalign ($(command -v kalign))"
  command -v hmmsearch >/dev/null 2>&1 && record_installed "Model surface dependency: hmmsearch ($(command -v hmmsearch))"
  command -v hmmbuild >/dev/null 2>&1 && record_installed "Model surface dependency: hmmbuild ($(command -v hmmbuild))"
}

ensure_java() {
  apt_get_safe update
  apt_get_safe install -y "${JAVA_PACKAGE}"

  if command -v java >/dev/null 2>&1; then
    log "Java available: $(java -version 2>&1 | sed -n '1p')"
  else
    fail "Java installation completed but java is not on PATH."
  fi
  record_installed "Java package: ${JAVA_PACKAGE}"
}

spark_target_dir() {
  printf '%s/%s\n' "${SPARK_ROOT}" "${SPARK_DIST}"
}

spark_release_matches() {
  local release_file="$1/RELEASE"
  [[ -f "${release_file}" ]] || return 1
  grep -Fq "Spark ${SPARK_VERSION}" "${release_file}"
}

ensure_spark() {
  require_cmd curl
  require_cmd tar

  local target_dir
  target_dir="$(spark_target_dir)"
  [[ -n "${SPARK_DIST}" && "${SPARK_DIST}" != */* ]] || fail "SPARK_DIST must be a distribution directory name, not a path."
  [[ -n "${SPARK_ROOT}" && "${SPARK_ROOT}" != "/" ]] || fail "SPARK_ROOT must not be empty or /."
  mkdir -p "${SPARK_ROOT}"

  if [[ -x "${target_dir}/bin/spark-submit" ]] && spark_release_matches "${target_dir}"; then
    log "Spark ${SPARK_VERSION} already available at ${target_dir}."
  else
    local tmp_dir archive_path
    tmp_dir="$(mktemp -d)"
    archive_path="${tmp_dir}/${SPARK_DIST}.tgz"

    log "Downloading Spark ${SPARK_VERSION} from ${SPARK_DOWNLOAD_URL}."
    curl -fL "${SPARK_DOWNLOAD_URL}" -o "${archive_path}"
    if is_enabled "${VERIFY_SPARK_SHA512}"; then
      log "Verifying Spark archive checksum."
      curl -fL "${SPARK_SHA512_URL}" -o "${archive_path}.sha512"
      (cd "${tmp_dir}" && sha512sum -c "${SPARK_DIST}.tgz.sha512")
    fi

    log "Installing Spark into ${SPARK_ROOT}."
    tar -xzf "${archive_path}" -C "${tmp_dir}"
    rm -rf "${target_dir}"
    mv "${tmp_dir}/${SPARK_DIST}" "${target_dir}"
    rm -rf "${tmp_dir}"
  fi

  local alias_path="${SPARK_ROOT}/spark-4"
  if [[ -L "${alias_path}" || ! -e "${alias_path}" ]]; then
    ln -sfn "${target_dir}" "${alias_path}"
  else
    log "Spark alias path exists and is not a symlink; leaving unchanged: ${alias_path}"
  fi
  log "Spark target: ${target_dir}"
  log "Spark alias: ${alias_path}"
  record_installed "Spark ${SPARK_VERSION}: ${target_dir}"
}

aws_cli_arch() {
  case "$(uname -m)" in
    x86_64 | amd64)
      printf '%s\n' "x86_64"
      ;;
    aarch64 | arm64)
      printf '%s\n' "aarch64"
      ;;
    *)
      fail "Unsupported AWS CLI architecture: $(uname -m)"
      ;;
  esac
}

session_manager_plugin_deb_url() {
  case "$(uname -m)" in
    x86_64 | amd64)
      printf '%s\n' "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/ubuntu_64bit/session-manager-plugin.deb"
      ;;
    aarch64 | arm64)
      printf '%s\n' "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/ubuntu_arm64/session-manager-plugin.deb"
      ;;
    *)
      fail "Unsupported Session Manager plugin architecture: $(uname -m)"
      ;;
  esac
}

ensure_session_manager_plugin() {
  require_cmd curl

  if command -v session-manager-plugin >/dev/null 2>&1; then
    log "AWS Session Manager plugin available: $(session-manager-plugin --version 2>&1)"
    record_installed "AWS Session Manager plugin: $(session-manager-plugin --version 2>&1)"
    return
  fi

  local tmp_dir deb_path
  tmp_dir="$(mktemp -d)"
  deb_path="${tmp_dir}/session-manager-plugin.deb"

  log "Downloading AWS Session Manager plugin."
  curl -fL "$(session_manager_plugin_deb_url)" -o "${deb_path}"
  sudo dpkg -i "${deb_path}"
  rm -rf "${tmp_dir}"

  require_cmd session-manager-plugin
  log "AWS Session Manager plugin available: $(session-manager-plugin --version 2>&1)"
  record_installed "AWS Session Manager plugin: $(session-manager-plugin --version 2>&1)"
}

ensure_aws_cli() {
  require_cmd curl
  require_cmd unzip

  local arch tmp_dir zip_path install_args
  arch="$(aws_cli_arch)"
  tmp_dir="$(mktemp -d)"
  zip_path="${tmp_dir}/awscliv2.zip"

  log "Downloading AWS CLI v2 installer for Linux ${arch}."
  curl -fL "https://awscli.amazonaws.com/awscli-exe-linux-${arch}.zip" -o "${zip_path}"
  unzip -q -u "${zip_path}" -d "${tmp_dir}"

  install_args=(--bin-dir /usr/local/bin --install-dir /usr/local/aws-cli)
  if [[ -d /usr/local/aws-cli ]]; then
    install_args+=(--update)
  fi

  sudo "${tmp_dir}/aws/install" "${install_args[@]}"
  rm -rf "${tmp_dir}"

  require_cmd aws
  log "AWS CLI available: $(aws --version 2>&1)"
  record_installed "AWS CLI: $(aws --version 2>&1)"
  ensure_session_manager_plugin
}

install_github_cli_repo() {
  require_cmd curl
  require_cmd dpkg

  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg >/dev/null
  sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg

  sudo tee /etc/apt/sources.list.d/github-cli.list >/dev/null <<EOF
deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main
EOF
}

ensure_github_cli() {
  if command -v gh >/dev/null 2>&1; then
    log "GitHub CLI available: $(gh --version | sed -n '1p')"
    record_installed "GitHub CLI: $(gh --version | sed -n '1p')"
    return
  fi

  install_github_cli_repo
  apt_get_safe update
  apt_get_safe install -y gh

  require_cmd gh
  log "GitHub CLI available: $(gh --version | sed -n '1p')"
  record_installed "GitHub CLI: $(gh --version | sed -n '1p')"
}

install_deb_url() {
  local name="$1"
  local url="$2"
  local tmp_dir

  require_cmd curl
  tmp_dir="$(mktemp -d)"
  log "Installing ${name} from ${url}."
  curl -fsSL "${url}" -o "${tmp_dir}/package.deb"
  sudo apt-get install -y "${tmp_dir}/package.deb"
  rm -rf "${tmp_dir}"
}

ensure_google_chrome() {
  if command -v google-chrome >/dev/null 2>&1; then
    log "Google Chrome available: $(google-chrome --version)"
    record_installed "Google Chrome: $(google-chrome --version)"
    return
  fi

  install_deb_url "Google Chrome" "https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb"
  require_cmd google-chrome
  record_installed "Google Chrome: $(google-chrome --version)"
}

ensure_vscode() {
  if command -v code >/dev/null 2>&1; then
    log "Visual Studio Code available: $(code --version | sed -n '1p')"
    record_installed "Visual Studio Code: $(code --version | sed -n '1p')"
    return
  fi

  install_deb_url "Visual Studio Code" "https://code.visualstudio.com/sha/download?build=stable&os=linux-deb-x64"
  require_cmd code
  record_installed "Visual Studio Code: $(code --version | sed -n '1p')"
}

vscode_extension_ids() {
  {
    printf '%s\n' "${VSCODE_EXTENSIONS[@]}"

    local extensions_path="${REPO_ROOT}/.vscode/extensions.json"
    if [[ -f "${extensions_path}" ]]; then
      if command -v python3 >/dev/null 2>&1; then
        python3 - "${extensions_path}" <<'PY'
import json
import sys
from pathlib import Path

try:
    data = json.loads(Path(sys.argv[1]).read_text())
except Exception:
    data = {}

for extension_id in data.get("recommendations", []):
    if isinstance(extension_id, str) and extension_id.strip():
        print(extension_id.strip())
PY
      elif command -v jq >/dev/null 2>&1; then
        jq -r '.recommendations[]? // empty' "${extensions_path}" 2>/dev/null || true
      fi
    fi
  } | awk 'NF && !seen[$0]++'
}

ensure_vscode_extensions() {
  require_cmd code

  local extension_id
  while IFS= read -r extension_id; do
    [[ -n "${extension_id}" ]] || continue
    log "Ensuring VS Code extension: ${extension_id}"
    if code --install-extension "${extension_id}" --force; then
      record_installed "VS Code extension: ${extension_id}"
    else
      log "VS Code extension install failed; continuing: ${extension_id}"
    fi
  done < <(vscode_extension_ids)
}

ensure_desktop_apps() {
  ensure_google_chrome
  ensure_vscode
  ensure_vscode_extensions
}

first_windows_aws_home() {
  if [[ -n "${WINDOWS_HOME}" ]]; then
    printf '%s\n' "${WINDOWS_HOME}"
    return
  fi

  local candidate
  for candidate in "/mnt/c/Users/${USER}" /mnt/c/Users/*; do
    if [[ -f "${candidate}/.aws/config" || -f "${candidate}/.aws/credentials" ]]; then
      printf '%s\n' "${candidate}"
      return
    fi
  done
}

copy_aws_config_file() {
  local src="$1"
  local dst="$2"
  local mode="$3"

  [[ -f "${src}" ]] || return 0
  if [[ -e "${dst}" ]] && ! is_enabled "${OVERWRITE_AWS_CONFIG}"; then
    log "AWS config target exists; leaving unchanged: ${dst}"
    return 0
  fi

  install -m "${mode}" "${src}" "${dst}"
  record_installed "Restored AWS config file: ${dst}"
}

restore_windows_aws_config() {
  local windows_home
  windows_home="$(first_windows_aws_home || true)"
  [[ -n "${windows_home}" ]] || {
    log "RESTORE_WINDOWS_AWS_CONFIG=1 but no Windows .aws directory was found under /mnt/c/Users."
    return
  }

  mkdir -p "${HOME}/.aws"
  chmod 700 "${HOME}/.aws"
  copy_aws_config_file "${windows_home}/.aws/config" "${HOME}/.aws/config" 600
  copy_aws_config_file "${windows_home}/.aws/credentials" "${HOME}/.aws/credentials" 600
}

install_gcp_cli_repo() {
  sudo install -m 0755 -d /usr/share/keyrings

  local tmp_key
  tmp_key="$(mktemp)"
  curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg -o "${tmp_key}"
  gpg --dearmor < "${tmp_key}" | sudo tee /usr/share/keyrings/cloud.google.gpg >/dev/null
  rm -f "${tmp_key}"
  sudo chmod a+r /usr/share/keyrings/cloud.google.gpg

  sudo tee /etc/apt/sources.list.d/google-cloud-sdk.list >/dev/null <<'EOF'
deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main
EOF
}

ensure_gcp_cli() {
  require_cmd curl
  require_cmd gpg

  install_gcp_cli_repo
  apt_get_safe update
  apt_get_safe install -y "${GCP_CLI_APT_PACKAGES[@]}"

  require_cmd gcloud
  log "Google Cloud CLI available: $(gcloud --version | sed -n '1p')"
  record_installed "Google Cloud CLI: $(gcloud --version | sed -n '1p')"
}

ubuntu_codename() {
  # shellcheck disable=SC1091
  source /etc/os-release
  if [[ -n "${UBUNTU_CODENAME:-}" ]]; then
    printf '%s\n' "${UBUNTU_CODENAME}"
    return
  fi
  if [[ -n "${VERSION_CODENAME:-}" ]]; then
    printf '%s\n' "${VERSION_CODENAME}"
    return
  fi
  lsb_release -cs
}

install_hashicorp_repo() {
  require_cmd curl
  require_cmd dpkg
  require_cmd gpg

  sudo install -m 0755 -d /usr/share/keyrings

  local keyring_path repo_path arch codename
  keyring_path="/usr/share/keyrings/hashicorp-archive-keyring.gpg"
  repo_path="/etc/apt/sources.list.d/hashicorp.list"
  arch="$(dpkg --print-architecture)"
  codename="$(ubuntu_codename)"

  download_openpgp_key "https://apt.releases.hashicorp.com/gpg" "${keyring_path}"

  sudo tee "${repo_path}" >/dev/null <<EOF
deb [arch=${arch} signed-by=${keyring_path}] https://apt.releases.hashicorp.com ${codename} main
EOF
}

ensure_terraform() {
  case "${TERRAFORM_INSTALL_METHOD}" in
    tfenv)
      ensure_terraform_tfenv
      ;;
    apt)
      ensure_terraform_apt
      ;;
    *)
      fail "Unknown TERRAFORM_INSTALL_METHOD: ${TERRAFORM_INSTALL_METHOD}. Use tfenv or apt."
      ;;
  esac
}

ensure_tfenv() {
  require_cmd curl
  require_cmd git
  require_cmd unzip

  if [[ -d "${TFENV_ROOT}/.git" ]]; then
    log "Updating tfenv at ${TFENV_ROOT}."
    if ! git -C "${TFENV_ROOT}" pull --ff-only; then
      log "tfenv update did not fast-forward; continuing with existing checkout."
    fi
  elif [[ -e "${TFENV_ROOT}" ]]; then
    fail "TFENV_ROOT exists but is not a git checkout: ${TFENV_ROOT}"
  else
    log "Installing tfenv into ${TFENV_ROOT}."
    git clone --depth 1 "${TFENV_GIT_URL}" "${TFENV_ROOT}"
  fi
}

ensure_terraform_tfenv() {
  ensure_tfenv
  ensure_tfenv_shell_config
  export TFENV_ROOT
  export PATH="${TFENV_ROOT}/bin:${PATH}"

  require_cmd tfenv

  tfenv install "${TERRAFORM_VERSION}"
  tfenv use "${TERRAFORM_VERSION}"

  require_cmd terraform
  log "Terraform available through tfenv: $(terraform version | sed -n '1p')"
  record_installed "tfenv: ${TFENV_ROOT}"
  record_installed "Terraform: $(terraform version | sed -n '1p')"
}

ensure_terraform_apt() {
  install_hashicorp_repo

  local package_version
  package_version="${TERRAFORM_VERSION}-1"

  apt_get_safe update
  apt_get_safe install -y --allow-downgrades --allow-change-held-packages "terraform=${package_version}"

  if is_enabled "${TERRAFORM_APT_HOLD}"; then
    sudo apt-mark hold terraform >/dev/null
  fi

  require_cmd terraform
  log "Terraform available: $(terraform version -json 2>/dev/null | jq -r '.terraform_version' 2>/dev/null || terraform version | sed -n '1p')"
  if is_enabled "${TERRAFORM_APT_HOLD}"; then
    log "Terraform package is held at ${package_version}. Set TERRAFORM_APT_HOLD=0 before install if you want apt upgrades to move it."
  fi
  record_installed "Terraform: $(terraform version | sed -n '1p')"
}

kubectl_client_version() {
  kubectl version --client=true 2>/dev/null | sed -n '1p'
}

download_openpgp_key() {
  local url="$1"
  local keyring_path="$2"
  local tmp_key
  tmp_key="$(mktemp)"

  curl -fsSL "${url}" -o "${tmp_key}"
  if ! grep -q "BEGIN PGP PUBLIC KEY BLOCK" "${tmp_key}"; then
    log "Downloaded key from ${url} was not an OpenPGP public key. First line:"
    sed -n '1p' "${tmp_key}" >&2 || true
    rm -f "${tmp_key}"
    return 1
  fi

  gpg --dearmor < "${tmp_key}" | sudo tee "${keyring_path}" >/dev/null
  rm -f "${tmp_key}"
  sudo chmod a+r "${keyring_path}"
}

install_kubectl_repo() {
  require_cmd curl
  require_cmd gpg

  sudo install -m 0755 -d /etc/apt/keyrings

  local keyring_path repo_path
  keyring_path="/etc/apt/keyrings/kubernetes-apt-keyring.gpg"
  repo_path="/etc/apt/sources.list.d/kubernetes.list"

  download_openpgp_key \
    "https://pkgs.k8s.io/core:/stable:/${KUBECTL_MINOR_VERSION}/deb/Release.key" \
    "${keyring_path}"

  sudo tee "${repo_path}" >/dev/null <<EOF
deb [signed-by=${keyring_path}] https://pkgs.k8s.io/core:/stable:/${KUBECTL_MINOR_VERSION}/deb/ /
EOF
}

install_helm_repo() {
  require_cmd curl
  require_cmd dpkg
  require_cmd gpg

  sudo install -m 0755 -d /usr/share/keyrings

  local keyring_path repo_path arch
  keyring_path="/usr/share/keyrings/helm.gpg"
  repo_path="/etc/apt/sources.list.d/helm-stable-debian.list"
  arch="$(dpkg --print-architecture)"

  download_openpgp_key \
    "https://packages.buildkite.com/helm-linux/helm-debian/gpgkey" \
    "${keyring_path}"

  sudo tee "${repo_path}" >/dev/null <<EOF
deb [arch=${arch} signed-by=${keyring_path}] https://packages.buildkite.com/helm-linux/helm-debian/any/ any main
EOF
}

ensure_kubernetes_cli() {
  install_kubectl_repo
  install_helm_repo

  apt_get_safe update
  apt_get_safe install -y kubectl helm

  require_cmd kubectl
  require_cmd helm

  log "kubectl available: $(kubectl_client_version)"
  log "Helm available: $(helm version --short)"
  record_installed "kubectl: $(kubectl_client_version)"
  record_installed "Helm: $(helm version --short)"
}

k9s_release_arch() {
  case "$(uname -m)" in
    x86_64 | amd64)
      printf '%s\n' "amd64"
      ;;
    aarch64 | arm64)
      printf '%s\n' "arm64"
      ;;
    armv7l | armv7)
      printf '%s\n' "armv7"
      ;;
    ppc64le)
      printf '%s\n' "ppc64le"
      ;;
    s390x)
      printf '%s\n' "s390x"
      ;;
    *)
      fail "Unsupported k9s architecture: $(uname -m)"
      ;;
  esac
}

k9s_archive_name() {
  printf 'k9s_Linux_%s.tar.gz\n' "$(k9s_release_arch)"
}

k9s_version_text() {
  k9s version --short 2>/dev/null | tr '\n' ' ' | sed -E 's/[[:space:]]+/ /g; s/[[:space:]]$//'
}

ensure_k9s() {
  require_cmd curl
  require_cmd tar

  if command -v k9s >/dev/null 2>&1 && k9s version --short 2>/dev/null | grep -Fq "${K9S_VERSION}"; then
    log "k9s already available: $(k9s_version_text)"
    record_installed "k9s: $(k9s_version_text)"
    return
  fi

  local archive_name tmp_dir archive_path
  archive_name="$(k9s_archive_name)"
  tmp_dir="$(mktemp -d)"
  archive_path="${tmp_dir}/${archive_name}"

  log "Downloading k9s ${K9S_VERSION} from ${K9S_DOWNLOAD_BASE_URL}/${archive_name}."
  if ! (
    set -euo pipefail
    cd "${tmp_dir}"
    curl -fL "${K9S_DOWNLOAD_BASE_URL}/${archive_name}" -o "${archive_path}"
    if is_enabled "${VERIFY_K9S_SHA256}"; then
      log "Verifying k9s archive checksum."
      curl -fL "${K9S_DOWNLOAD_BASE_URL}/checksums.sha256" -o checksums.sha256
      awk -v archive="${archive_name}" '$2 == archive { print; found = 1 } END { exit found ? 0 : 1 }' checksums.sha256 | sha256sum -c -
    fi
    tar -xzf "${archive_path}" -C "${tmp_dir}" k9s
    sudo install -d -m 0755 "${K9S_INSTALL_DIR}"
    sudo install -m 0755 "${tmp_dir}/k9s" "${K9S_INSTALL_DIR}/k9s"
  ); then
    rm -rf "${tmp_dir}"
    return 1
  fi
  rm -rf "${tmp_dir}"

  export PATH="${K9S_INSTALL_DIR}:${PATH}"
  require_cmd k9s
  log "k9s available: $(k9s_version_text)"
  record_installed "k9s: $(k9s_version_text)"
}

run_sibling_script() {
  local script_name="$1"
  shift
  local script_path="${SCRIPT_DIR}/${script_name}"
  [[ -x "${script_path}" ]] || fail "Expected executable script: ${script_path}"
  "${script_path}" "$@"
}

ensure_docker() {
  run_sibling_script install_docker_wsl_ubuntu.sh
  record_installed "Docker stack via install_docker_wsl_ubuntu.sh"
}

ensure_nvidia() {
  run_sibling_script install_nvidia_container_toolkit_wsl_ubuntu.sh
  record_installed "NVIDIA Container Toolkit via install_nvidia_container_toolkit_wsl_ubuntu.sh"
}

verify_native_nvidia_gpu() {
  require_cmd nvidia-smi

  log "Checking native WSL GPU visibility with nvidia-smi -L."
  local gpu_list
  if gpu_list="$(nvidia-smi -L 2>&1)"; then
    printf '%s\n' "${gpu_list}"
    record_installed "Native WSL GPU visible: ${gpu_list%%$'\n'*}"
    return
  fi

  fail "Native WSL GPU access is not healthy: ${gpu_list}

This must work before Docker GPU containers can work.
Fix WSL GPU access first, then rerun:
  1. From Windows PowerShell: wsl --shutdown
  2. Reopen WSL and run: nvidia-smi -L
  3. If it still fails, check the Windows NVIDIA driver / reboot Windows."
}

detect_cuda_home() {
  local candidate
  for candidate in "${CUDA_HOME:-}" /usr/local/cuda /usr/lib/cuda /usr/lib/nvidia-cuda-toolkit; do
    [[ -n "${candidate}" ]] || continue
    if [[ -d "${candidate}" ]] && [[ -x "${candidate}/bin/nvcc" ]]; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done

  if command -v nvcc >/dev/null 2>&1; then
    local nvcc_path
    nvcc_path="$(readlink -f "$(command -v nvcc)")"
    candidate="$(cd "$(dirname "${nvcc_path}")/.." && pwd)"
    if [[ -d "${candidate}" ]]; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  fi

  return 1
}

repair_debian_cuda_toolkit_layout() {
  local cuda_home="/usr/lib/cuda"
  local nvcc_path="/usr/lib/nvidia-cuda-toolkit/bin/nvcc"

  if [[ -d "${cuda_home}" && ! -x "${cuda_home}/bin/nvcc" && -x "${nvcc_path}" ]]; then
    log "Linking Debian CUDA nvcc into ${cuda_home}/bin for PyTorch extension builds."
    sudo mkdir -p "${cuda_home}/bin"
    sudo ln -sf "${nvcc_path}" "${cuda_home}/bin/nvcc"
  fi
}

write_cuda_profile() {
  local cuda_home="$1"
  local lib_path
  local compiler_block=""
  lib_path="${cuda_home}/lib64"
  if [[ ! -d "${lib_path}" && -d "${cuda_home}/lib" ]]; then
    lib_path="${cuda_home}/lib"
  fi

  if [[ -x "${CUDA_HOST_CC}" && -x "${CUDA_HOST_CXX}" ]]; then
    compiler_block="export CC=\"${CUDA_HOST_CC}\"
export CXX=\"${CUDA_HOST_CXX}\"
export CUDAHOSTCXX=\"${CUDA_HOST_CXX}\""
  fi

  sudo tee /etc/profile.d/wielder-cuda.sh >/dev/null <<EOF
# Wielder managed CUDA toolkit discovery for local model extension builds.
export CUDA_HOME="${cuda_home}"
export CUDA_PATH="\${CUDA_HOME}"
export PATH="\${CUDA_HOME}/bin:\${PATH}"
if [ -d "${lib_path}" ]; then
  export LD_LIBRARY_PATH="${lib_path}:\${LD_LIBRARY_PATH:-}"
fi
${compiler_block}
EOF
}

ensure_shells_source_cuda_profile() {
  local rc_path
  local line='[[ -f /etc/profile.d/wielder-cuda.sh ]] && source /etc/profile.d/wielder-cuda.sh'

  for rc_path in "${HOME}/.zshrc" "${HOME}/.bashrc"; do
    touch "${rc_path}"
    if ! grep -Fq "${line}" "${rc_path}"; then
      {
        printf '\n'
        printf '# Wielder CUDA toolkit for local model extension builds.\n'
        printf '%s\n' "${line}"
      } >>"${rc_path}"
      record_installed "Shell config CUDA profile: ${rc_path}"
    fi
  done
}

ensure_cuda_toolkit() {
  verify_native_nvidia_gpu

  if ! command -v nvcc >/dev/null 2>&1; then
    log "Installing host CUDA toolkit package: ${CUDA_TOOLKIT_PACKAGE}"
    apt_get_safe update
    apt_get_safe install -y "${CUDA_TOOLKIT_PACKAGE}"
  fi

  require_cmd nvcc
  repair_debian_cuda_toolkit_layout

  if [[ ! -x "${CUDA_HOST_CC}" || ! -x "${CUDA_HOST_CXX}" ]]; then
    log "Installing CUDA-supported host compiler packages: ${CUDA_HOST_GCC_PACKAGE} ${CUDA_HOST_GXX_PACKAGE}"
    apt_get_safe update
    apt_get_safe install -y "${CUDA_HOST_GCC_PACKAGE}" "${CUDA_HOST_GXX_PACKAGE}"
  fi

  local cuda_home
  cuda_home="$(detect_cuda_home)" || fail "CUDA toolkit is installed, but CUDA_HOME could not be detected."
  write_cuda_profile "${cuda_home}"
  ensure_shells_source_cuda_profile

  # shellcheck disable=SC1091
  source /etc/profile.d/wielder-cuda.sh

  nvcc --version

  if [[ -x "${WORKSPACE_VENV_PATH}/bin/python" ]]; then
    "${WORKSPACE_VENV_PATH}/bin/python" - <<'PY'
import os
import torch
from torch.utils.cpp_extension import CUDA_HOME

print(f"torch: {torch.__version__}")
print(f"torch.version.cuda: {torch.version.cuda}")
print(f"torch.cuda.is_available: {torch.cuda.is_available()}")
print(f"CUDA_HOME env: {os.environ.get('CUDA_HOME')}")
print(f"torch cpp_extension CUDA_HOME: {CUDA_HOME}")

if not torch.cuda.is_available():
    raise SystemExit("torch cannot see CUDA")
if CUDA_HOME is None:
    raise SystemExit("torch cpp_extension still cannot resolve CUDA_HOME")
PY
  fi

  record_installed "Host CUDA toolkit: ${cuda_home}"
}

ensure_gpu_stack() {
  local script_path="${SCRIPT_DIR}/install_local_gpu_container_stack_wsl_ubuntu.sh"
  [[ -x "${script_path}" ]] || fail "Expected executable script: ${script_path}"

  verify_native_nvidia_gpu
  ENABLE_NESTED_GPU_HANDOFF="${ENABLE_NESTED_GPU_HANDOFF:-1}" "${script_path}"
  record_installed "Local Docker GPU stack via install_local_gpu_container_stack_wsl_ubuntu.sh"
}

ensure_kind() {
  CREATE_CLUSTER="${CREATE_CLUSTER:-0}" RECREATE_CLUSTER="${RECREATE_CLUSTER:-0}" \
    "${SCRIPT_DIR}/install_kind_wsl_ubuntu.sh"
  record_installed "kind via install_kind_wsl_ubuntu.sh"
}

ensure_kind_gpu() {
  CREATE_CLUSTER="${CREATE_CLUSTER:-0}" RECREATE_CLUSTER="${RECREATE_CLUSTER:-0}" \
    "${SCRIPT_DIR}/install_kind_gpu_wsl_ubuntu.sh"
  record_installed "GPU kind tooling via install_kind_gpu_wsl_ubuntu.sh"
}

ensure_k3d() {
  run_sibling_script install_k3d_wsl_ubuntu.sh
  record_installed "k3d via install_k3d_wsl_ubuntu.sh"
}

ensure_azure_cli() {
  run_sibling_script install_azure_cli_wsl_ubuntu.sh
  record_installed "Azure CLI via install_azure_cli_wsl_ubuntu.sh"
}

ensure_visualizer() {
  run_sibling_script install_visualizer_wsl_ubuntu.sh
  record_installed "Visualizer helpers via install_visualizer_wsl_ubuntu.sh"
}

print_summary() {
  local python_bin spark_dir
  python_bin="$(venv_python)"
  spark_dir="$(spark_target_dir)"

  cat <<EOF

Completed Ubuntu/WSL installation plan.

Workspace:
  repo root: ${REPO_ROOT}
  venv: ${WORKSPACE_VENV_PATH}
  python: ${python_bin}

Spark:
  configured target: ${spark_dir}
  auto-detect alias: ${SPARK_ROOT}/spark-4

Cloud CLI auth:
  AWS config restore from Windows is optional:
    RESTORE_WINDOWS_AWS_CONFIG=1 ${SCRIPT_DIR}/install_ubuntu.sh
  AWS config restore only:
    AWS_CONFIG_RESTORE_ONLY=1 OVERWRITE_AWS_CONFIG=1 ${SCRIPT_DIR}/install_ubuntu.sh
  AWS verification after auth/config restore:
    AWS_PROFILE=<profile-name> aws sts get-caller-identity
  AWS MFA profile refresh:
    AWS_PROFILE=gid-cli-user-mfa aws sts get-caller-identity
  AWS long session profile:
    set [default] + gid-cli-user-mfa duration_seconds=43200 in ~/.aws/config and the IAM role max session duration to 12 hours
  AWS Session Manager plugin:
    session-manager-plugin --version
  GitHub interactive auth after install:
    gh auth login
    gh auth setup-git
  Terraform/Wielder MFA shell:
    helper="\$(find "${REPO_ROOT}" -path '*/scripts/export_terraform_aws_env.py' -print -quit)" && eval "\$("\${helper}" -cc default_conf)"
  GCP interactive auth after install:
    gcloud init
    gcloud auth application-default login

Focused phases:
  ${SCRIPT_DIR}/install_ubuntu.sh --only python-env
  ${SCRIPT_DIR}/install_ubuntu.sh --only python-workspace
  ${SCRIPT_DIR}/install_ubuntu.sh --only nodejs
  ${SCRIPT_DIR}/install_ubuntu.sh --only model-artifact-tools
  ${SCRIPT_DIR}/install_ubuntu.sh --only model-launcher
  ${SCRIPT_DIR}/install_ubuntu.sh --only model-surface-deps
  ${SCRIPT_DIR}/install_ubuntu.sh --only shell-config
  ${SCRIPT_DIR}/install_ubuntu.sh --only desktop-apps
  ${SCRIPT_DIR}/install_ubuntu.sh --only kubernetes-cli
  ${SCRIPT_DIR}/install_ubuntu.sh --only k9s
  ${SCRIPT_DIR}/install_ubuntu.sh --only terraform

Optional phases:
  ${SCRIPT_DIR}/install_ubuntu.sh --only cuda-toolkit
  ${SCRIPT_DIR}/install_ubuntu.sh --only gpu-stack
  ${SCRIPT_DIR}/install_ubuntu.sh --only docker
  ${SCRIPT_DIR}/install_ubuntu.sh --only nvidia
  ${SCRIPT_DIR}/install_ubuntu.sh --only kind
  ${SCRIPT_DIR}/install_ubuntu.sh --only kind-gpu
  ${SCRIPT_DIR}/install_ubuntu.sh --only k3d
  ${SCRIPT_DIR}/install_ubuntu.sh --only azure-cli
  ${SCRIPT_DIR}/install_ubuntu.sh --only visualizer

uv venv shell helpers:
  uvenv activate              # activate the configured default venv
  uvenv activate /path/.venv  # activate any uv-created venv
  uvenv create experiment     # create ${HOME}/.uvenvs/experiment
  uvenv deactivate

The managed .bashrc/.zshrc block auto-activates:
  ${WORKSPACE_VENV_PATH}

EOF

  printf '%s\n' "${LIGHT_BLUE}Installed or updated in this run:${RESET_COLOR}"
  if ((${#INSTALLED_ITEMS[@]} == 0)); then
    printf '%s\n' "${LIGHT_BLUE}  - No install phases were enabled.${RESET_COLOR}"
  else
    local item
    for item in "${INSTALLED_ITEMS[@]}"; do
      printf '%s\n' "${LIGHT_BLUE}  - ${item}${RESET_COLOR}"
    done
  fi
}

main() {
  parse_args "$@"

  log "$0 is running from: ${SCRIPT_DIR}"
  log "Repository root: ${REPO_ROOT}"

  ensure_ubuntu

  if is_enabled "${AWS_CONFIG_RESTORE_ONLY}"; then
    run_step "aws config restore" restore_windows_aws_config
    print_summary
    return
  fi

  is_enabled "${INSTALL_BASE}" && run_step "apt basics" ensure_base_packages
  is_enabled "${INSTALL_UV}" && run_step "uv" ensure_uv
  is_enabled "${INSTALL_PYTHON_ENV}" && run_step "python env" ensure_python_env
  is_enabled "${INSTALL_DIRECT_URL_REQUIREMENTS}" && run_step "direct url requirements" ensure_direct_url_requirements
  is_enabled "${INSTALL_WORKSPACE_PACKAGES}" && run_step "workspace packages" ensure_workspace_packages
  is_enabled "${INSTALL_NODEJS}" && run_step "nodejs" ensure_nodejs
  is_enabled "${INSTALL_MODEL_ARTIFACT_TOOLS}" && run_step "model artifact tools" ensure_model_artifact_tools
  is_enabled "${INSTALL_MODEL_LAUNCHER}" && run_step "model launcher web deps" ensure_model_launcher_web_deps
  is_enabled "${INSTALL_MODEL_SURFACE_DEPS}" && run_step "model surface deps" ensure_model_surface_deps
  is_enabled "${INSTALL_IDE_CONFIGS}" && run_step "ide configs" render_ide_configs
  is_enabled "${INSTALL_SHELL_CONFIG}" && run_step "shell config" render_shell_config
  is_enabled "${INSTALL_JAVA}" && run_step "java" ensure_java
  is_enabled "${INSTALL_SPARK}" && run_step "spark" ensure_spark
  is_enabled "${INSTALL_AWS_CLI}" && run_step "aws cli" ensure_aws_cli
  is_enabled "${INSTALL_GITHUB_CLI}" && run_step "github cli" ensure_github_cli
  is_enabled "${INSTALL_GCP_CLI}" && run_step "google cloud cli" ensure_gcp_cli
  is_enabled "${INSTALL_TERRAFORM}" && run_step "terraform" ensure_terraform
  is_enabled "${INSTALL_KUBERNETES_CLI}" && run_step "kubernetes cli" ensure_kubernetes_cli
  is_enabled "${INSTALL_K9S}" && run_step "k9s" ensure_k9s
  is_enabled "${INSTALL_DESKTOP_APPS}" && run_step "desktop apps" ensure_desktop_apps
  if ! is_enabled "${INSTALL_DESKTOP_APPS}" && is_enabled "${INSTALL_VSCODE_EXTENSIONS}"; then
    run_step "vscode extensions" ensure_vscode_extensions
  fi
  is_enabled "${INSTALL_CUDA_TOOLKIT}" && run_step "cuda toolkit" ensure_cuda_toolkit
  is_enabled "${RESTORE_WINDOWS_AWS_CONFIG}" && run_step "aws config restore" restore_windows_aws_config

  if is_enabled "${INSTALL_GPU_STACK}"; then
    run_step "local gpu container stack" ensure_gpu_stack
  else
    is_enabled "${INSTALL_DOCKER}" && run_step "docker" ensure_docker
    is_enabled "${INSTALL_NVIDIA}" && run_step "nvidia container toolkit" ensure_nvidia
  fi
  is_enabled "${INSTALL_KIND}" && run_step "kind" ensure_kind
  is_enabled "${INSTALL_KIND_GPU}" && run_step "kind gpu" ensure_kind_gpu
  is_enabled "${INSTALL_K3D}" && run_step "k3d" ensure_k3d
  is_enabled "${INSTALL_AZURE_CLI}" && run_step "azure cli" ensure_azure_cli
  is_enabled "${INSTALL_VISUALIZER}" && run_step "visualizer helpers" ensure_visualizer

  print_summary
}

main "$@"
