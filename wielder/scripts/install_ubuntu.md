# Ubuntu/WSL Installer

`install_ubuntu.sh` is the consolidated Ubuntu/WSL workstation bootstrapper.
It is intended to work from any current directory and resolves all sibling
scripts through its own location.

The script is deliberately shaped like a Dockerfile: each phase is explicit,
ordered, repeatable, and safe to rerun. Phases install or update rather than
assuming a clean machine.

## Default Phases

By default, the script runs:

1. Ubuntu base packages, starting with `curl`, `wget`, `git`, `ca-certificates`,
   `gnupg`, build tools, archive tools, and common Python native build headers.
2. `uv` installation/update into `~/.local/bin`.
3. Python `3.11.11` installation through `uv`.
4. A uv-managed virtual environment at the repository root: `.venv`, including
   `ipykernel` and `jupyter` for notebooks.
5. Project-provided direct Git URL Python requirements, when configured.
6. Editable installs for the Workspace workspace projects.
7. VS Code and Pyright settings bound to `.venv`.
8. Managed `.bashrc` and `.zshrc` blocks that source Wielder's generic `uvenv`
   helper and auto-activate the configured workspace `.venv`.
9. Model artifact tooling: `rclone`, `zstd` for Ollama archive extraction, the
   Hugging Face CLI package in the workspace `.venv`, and Ollama.
10. Java 17 through apt.
11. Spark `4.0.1` under `~/opt`, with `~/opt/spark-4` pointing to the active
   Spark installation.
12. AWS CLI v2 using the official AWS Linux installer.
13. Google Cloud CLI using the official Google apt repository.
14. Latest stable Terraform through `tfenv`.
15. `kubectl` and Helm through their official apt repositories.
16. kind local Kubernetes tooling through `install_kind_wsl_ubuntu.sh`, with
    conservative defaults that do not create or recreate a cluster.

The default command is:

```bash
<workspace>/Wielder/wielder/scripts/install_ubuntu.sh
```

To run the default control-plane install and add an optional phase such as
Docker:

```bash
<workspace>/Wielder/wielder/scripts/install_ubuntu.sh --with docker
```

## Focused Phases

To install only the shell helpers before the workspace `.venv` exists:

```bash
<workspace>/Wielder/wielder/scripts/install_ubuntu.sh --only shell-config
source ~/.bashrc   # or: source ~/.zshrc
```

The managed shell block will quietly skip auto-activation until the configured
venv exists.

To create or repair only the uv-managed workspace `.venv`:

```bash
<workspace>/Wielder/wielder/scripts/install_ubuntu.sh --only python-env
```

To create the `.venv` and install the editable Python workspace packages:

```bash
<workspace>/Wielder/wielder/scripts/install_ubuntu.sh --only python-workspace
```

To install only `kubectl` and Helm without rerunning Python, Spark, or cloud CLI
phases:

```bash
<workspace>/Wielder/wielder/scripts/install_ubuntu.sh --only kubernetes-cli
```

To install only Terraform:

```bash
<workspace>/Wielder/wielder/scripts/install_ubuntu.sh --only terraform
```

To install only model artifact tools:

```bash
<workspace>/Wielder/wielder/scripts/install_ubuntu.sh --only model-artifact-tools
```

This phase installs `rclone` and `zstd`, installs the Hugging Face CLI package
into the workspace `.venv`, and installs Ollama if it is not already available.
The versioned rclone/model account contract lives in:

```text
<workspace>/workflow-wielder/conf/model_artifacts.conf
```

Account selection is HOCON-owned. Override `model_artifacts.active_account` and
related non-secret fields from a local `developer.conf`; keep tokens in the
normal provider auth stores or environment-backed login surfaces.

## Optional Phases

Optional phases are disabled by default because they mutate local services,
container runtimes, cloud authentication surfaces, or Kubernetes state. The kind
phase is enabled by default for local Wielder readiness, but cluster creation is
still disabled unless explicitly requested.

```bash
<workspace>/Wielder/wielder/scripts/install_ubuntu.sh --only cuda-toolkit
<workspace>/Wielder/wielder/scripts/install_ubuntu.sh --only gpu-stack
<workspace>/Wielder/wielder/scripts/install_ubuntu.sh --only docker
<workspace>/Wielder/wielder/scripts/install_ubuntu.sh --only nvidia
<workspace>/Wielder/wielder/scripts/install_ubuntu.sh --only kind-gpu
<workspace>/Wielder/wielder/scripts/install_ubuntu.sh --only k3d
<workspace>/Wielder/wielder/scripts/install_ubuntu.sh --only model-launcher
<workspace>/Wielder/wielder/scripts/install_ubuntu.sh --only model-surface-deps
<workspace>/Wielder/wielder/scripts/install_ubuntu.sh --only azure-cli
<workspace>/Wielder/wielder/scripts/install_ubuntu.sh --only visualizer
```

For model-runtime Docker GPU paths, use the combined phase:

```bash
<workspace>/Wielder/wielder/scripts/install_ubuntu.sh --only gpu-stack
```

Local model-runtime runs may use the workspace `.venv`, not only Docker. They
therefore need the host CUDA toolkit and `CUDA_HOME`, while Docker GPU
containers need the NVIDIA Container Toolkit. The `gpu-stack` phase includes
both; to repair only the host CUDA precondition, run:

```bash
<workspace>/Wielder/wielder/scripts/install_ubuntu.sh --only cuda-toolkit
```

Both phases check native WSL GPU visibility first:

```bash
nvidia-smi -L
```

The CUDA toolkit phase installs `nvidia-cuda-toolkit`, writes
`/etc/profile.d/workspace-cuda.sh`, ensures new `bash` and `zsh` shells source it, and
validates that PyTorch can resolve `torch.utils.cpp_extension.CUDA_HOME`. On
Ubuntu/Debian installs where headers live under `/usr/lib/cuda` but `nvcc`
lives under `/usr/lib/nvidia-cuda-toolkit/bin`, it links `nvcc` into
`/usr/lib/cuda/bin` so PyTorch extension builds see one coherent CUDA root.
Because CUDA 12.4 rejects newer host compilers, the phase also installs/selects
`gcc-13`/`g++-13` through the same profile file for local model extension
builds.
The combined GPU phase then installs or updates Docker, configures the NVIDIA
Container Toolkit, restarts Docker, and runs the CUDA container smoke tests.
Nested GPU handoff for kind/k3d is enabled by default for this combined phase.
Disable it with:

```bash
ENABLE_NESTED_GPU_HANDOFF=0 INSTALL_GPU_STACK=1 <workspace>/Wielder/wielder/scripts/install_ubuntu.sh
```

For kind and kind-gpu, the consolidated installer only prepares tooling by
default:

```bash
CREATE_CLUSTER=0
RECREATE_CLUSTER=0
```

Do not use shell-prefix environment variables as the normal operator control
surface. Cluster identity and host ports belong in resolved Wielder config. Let
the Wielder provisioner create the configured cluster from the active ecosystem.

To rerun only the kind tooling phase:

```bash
<workspace>/Wielder/wielder/scripts/install_ubuntu.sh --only kind
```

To create a configured local hybrid model-runtime kind cluster, use the workflow
entrypoint with the desired Wielder modes, for example:

```bash
<workspace>/workflow-wielder/src/workspace_wielder/deploy/apps/model_binding_workflow/wield/model_binding_workflow_deploy.py \
  -es kind_hybrid_model_binding \
  -st dev \
  -se org \
  -dl standard \
  -cn standard \
  -cc default_conf \
  -w apply
```

## Legacy Coverage

This script intentionally does not blindly copy every action from the old
`useful/prepare_ubuntu*.sh` scripts. The old scripts mix modern workstation
setup with obsolete versions, interactive actions, and cluster mutations.

Covered directly:

- Base apt/build tooling
- `uv` and the Workspace Python environment
- Editable Workspace workspace installs
- Java 17
- Spark 4
- AWS CLI v2
- Google Cloud CLI
- Terraform
- `kubectl`
- Helm

Covered by optional delegated scripts:

- Combined local Docker GPU stack
- Docker
- NVIDIA Container Toolkit
- kind / GPU kind
- k3d
- Azure CLI
- Graphviz/browser visualizer helpers

Not yet folded into this consolidated path:

- Scala and Maven
- Helm repository registration
- Lens desktop app
- metrics-server mutation
- SSH key generation
- pyenv/jenv installation

Those can be added as explicit phases if they are still part of the current
Workspace workstation contract.

Intentionally retired from this path:

- Perl and CPAN helper libraries

## Common Overrides

```bash
WORKSPACE_PYTHON_VERSION=3.11.11
WORKSPACE_VENV_PATH=<workspace>/.venv
RECREATE_VENV=0
WORKSPACE_LOCALE=en_US.UTF-8
UV_INSTALL_DIR=/home/gideon/.local/bin
DIRECT_URL_REQUIREMENTS_CSV=<requirement-spec>
INSTALL_DIRECT_URL_REQUIREMENTS=1
INSTALL_IDE_CONFIGS=1
INSTALL_SHELL_CONFIG=1
JAVA_PACKAGE=openjdk-17-jdk
SPARK_VERSION=4.0.1
SPARK_DIST=spark-4.0.1-bin-hadoop3
SPARK_ROOT=/home/gideon/opt
VERIFY_SPARK_SHA512=1
INSTALL_AWS_CLI=1
INSTALL_GCP_CLI=1
INSTALL_TERRAFORM=1
TERRAFORM_VERSION=latest
TERRAFORM_INSTALL_METHOD=tfenv
TFENV_ROOT=/home/gideon/.tfenv
TERRAFORM_APT_HOLD=0
INSTALL_KUBERNETES_CLI=1
KUBECTL_MINOR_VERSION=v1.33
RESTORE_WINDOWS_AWS_CONFIG=0
AWS_CONFIG_RESTORE_ONLY=0
OVERWRITE_AWS_CONFIG=0
WINDOWS_HOME=
```

## Cloud CLIs and Auth

The installer installs the AWS and GCP command-line tools, but it does not run
interactive login flows by default.

AWS CLI v2 is installed from the official AWS zip installer and updated through
the same installer path on reruns. If the Windows AWS profile still exists, the
installer can copy it into WSL:

```bash
RESTORE_WINDOWS_AWS_CONFIG=1 <workspace>/Wielder/wielder/scripts/install_ubuntu.sh
```

To restore only the AWS config without rerunning the workstation install:

```bash
AWS_CONFIG_RESTORE_ONLY=1 <workspace>/Wielder/wielder/scripts/install_ubuntu.sh
```

If `~/.aws/config` or `~/.aws/credentials` already exists, the installer leaves
it alone unless this is also set:

```bash
OVERWRITE_AWS_CONFIG=1
```

For a wiped or stale WSL auth state, the usual repair command is:

```bash
AWS_CONFIG_RESTORE_ONLY=1 OVERWRITE_AWS_CONFIG=1 <workspace>/Wielder/wielder/scripts/install_ubuntu.sh
```

After restore or manual auth, verify AWS with:

```bash
AWS_PROFILE=<profile-name> aws sts get-caller-identity
```

If there is no `[default]` profile in `~/.aws/credentials`, plain `aws ...`
commands will fail with `NoCredentials`. Use one of the named profiles or export
one in the shell:

```bash
AWS_PROFILE=gid-cli-user aws sts get-caller-identity
export AWS_PROFILE=gid-cli-user
```

For this workstation, the AWS role profile is MFA-backed. The profile documented
in the Workspace examples is:

```text
gid-cli-user-mfa
```

Use a long-lived CLI role session for operator work:

```ini
[default]
source_profile = gid-cli-user
mfa_serial = arn:aws:iam::<account-id>:mfa/<device-name>
role_arn = arn:aws:iam::<account-id>:role/cli-mfa-role
region = us-east-2
output = json
duration_seconds = 43200

[profile gid-cli-user-mfa]
source_profile = gid-cli-user
mfa_serial = arn:aws:iam::<account-id>:mfa/<device-name>
role_arn = arn:aws:iam::<account-id>:role/cli-mfa-role
region = us-east-2
output = json
duration_seconds = 43200
```

`duration_seconds = 43200` requests 12 hours. The IAM role must also have its
maximum session duration set to 12 hours; otherwise AWS will cap or reject the
requested duration.

The `[default]` role profile is intentional on Workspace operator workstations, so
plain `aws ...` commands work without an `AWS_PROFILE=...` prefix.

Session Manager also requires the local AWS Session Manager plugin:

```bash
session-manager-plugin --version
```

Refreshing that profile is intentionally interactive:

```bash
AWS_PROFILE=gid-cli-user-mfa aws sts get-caller-identity
AWS_PROFILE=gid-cli-user-mfa aws s3 ls
```

Wielder/Terraform flows use the AWS CLI MFA cache rather than hardcoding session
exports in `.zshrc`. The documented shell handoff is:

```bash
eval "$(<workspace>/workspace-provision/scripts/export_terraform_aws_env.py -cc default_conf)"
```

That helper expects an ignored local overlay at:

```text
workflow-wielder/conf/context_conf/default_conf/secrets.conf
```

with:

```hocon
aws_cli_profile = "gid-cli-user-mfa"
```

The tracked example lives at:

```text
workflow-wielder/conf/context_conf_examples/secrets.conf.example
```

Google Cloud CLI is installed from Google's apt repository as
`google-cloud-cli`. After installation, initialize and restore local ADC with:

```bash
gcloud init
gcloud auth application-default login
gcloud config set project workspace-dev
```

## Terraform

The installer installs Terraform through `tfenv` by default. This is required
for Wielder infrastructure actions such as AWS super-cluster and EMR cleanup.

The installer installs and selects Terraform `latest` by default. It does not
write `.terraform-version`; projects that need a durable selector should store it
in their Wielder/provisioning configuration and enforce compatibility with
Terraform `required_version` inside their stacks.

Focused install:

```bash
<workspace>/Wielder/wielder/scripts/install_ubuntu.sh --only terraform
```

The managed shell block adds `~/.tfenv/bin` before system paths, so an existing
apt Terraform such as `/usr/bin/terraform` will not win in new shells. The
focused `--only terraform` phase also appends a small tfenv block to `~/.zshrc`
and `~/.bashrc` when the managed block is not present yet. For the current
shell, run:

```bash
source ~/.zshrc   # or: source ~/.bashrc
rehash            # bash equivalent: hash -r
terraform version
```

To use the apt package path instead:

```bash
TERRAFORM_INSTALL_METHOD=apt TERRAFORM_APT_HOLD=1 <workspace>/Wielder/wielder/scripts/install_ubuntu.sh --only terraform
```

## Kubernetes CLI Tooling

The installer installs `kubectl` and Helm by default because Wielder deploy and
delete entrypoints use them for both local kind clusters and remote EKS
contexts.

`kubectl` is installed from the Kubernetes package repository for:

```bash
KUBECTL_MINOR_VERSION=v1.33
```

Helm is installed from the current Helm Debian/Ubuntu package repository hosted
through Buildkite. The older `baltocdn.com/helm` key endpoint is not used by
this installer.

That keeps the CLI aligned with the current Workspace EKS generation while still
allowing apt to install the latest patch in that minor line. Override it before
running the script when you need a different supported minor:

```bash
KUBECTL_MINOR_VERSION=v1.34 <workspace>/Wielder/wielder/scripts/install_ubuntu.sh
```

To skip this phase:

```bash
<workspace>/Wielder/wielder/scripts/install_ubuntu.sh --skip kubernetes-cli
```

## Python Direction

This installer starts the migration from `pyenv` to `uv` without forcing a
monorepo packaging rewrite. It preserves the current editable-install workflow,
but replaces pyenv activation with:

```bash
uv python install 3.11.11
uv venv --python 3.11.11 .venv
uv pip install --python .venv/bin/python -e <project>
```

The installer also sources Wielder's generic `uvenv` helper from managed
`.bashrc` and `.zshrc` blocks. `uvenv` is not Workspace-specific; the Workspace
installer sets a default virtualenv path and a friendly default name derived
from the repository folder only when an earlier shell block has not already
chosen defaults. `WORKSPACE_UVENV_NAME` overrides the derived friendly name:

```bash
uvenv activate              # activate the configured default venv
uvenv activate culture      # activate the configured default by friendly name
uvenv activate .venv        # activate a venv by path
uvenv activate experiment   # activate ./experiment, ./.experiment, or ~/.uvenvs/experiment
uvenv create experiment     # create ~/.uvenvs/experiment with uv
uvenv deactivate
uvenv current
uvenv list
```

Short aliases are also available:

```bash
uvenv-activate .venv
uvenv-deactivate
uv-activate .venv
uv-deactivate
```

The older `package_py.sh` flow still exists, but this installer should become
the Ubuntu/WSL path once the uv workflow is validated on a real workstation.

Some workspace packages may depend on direct Git URL dependencies. `uv` requires
URL dependencies to be direct requirements or constraints, so this installer can
install configured URL dependencies before editable workspace packages.

Project-specific direct URL requirements should be supplied outside generic
Wielder code, for example:

```bash
DIRECT_URL_REQUIREMENTS_CSV='<package> @ git+https://example.invalid/org/repo.git@v1.0.0' \
  <workspace>/Wielder/wielder/scripts/install_ubuntu.sh --only direct-url-requirements
```

Existing virtual environments are reused when their Python version matches
`WORKSPACE_PYTHON_VERSION`. To deliberately replace the environment:

```bash
RECREATE_VENV=1 <workspace>/Wielder/wielder/scripts/install_ubuntu.sh
```

## VS Code and Pyright

The installer writes repo-local IDE configuration for the uv-managed environment:

```text
.vscode/settings.json
.vscode/extensions.json
pyrightconfig.json
```

The interpreter is set to:

```text
${workspaceFolder}/.venv/bin/python
```

The extension recommendations include:

```text
ms-python.python
ms-toolsai.jupyter
ms-toolsai.jupyter-keymap
ms-toolsai.jupyter-renderers
```

The Pyright config uses:

```json
{
  "venvPath": ".",
  "venv": ".venv",
  "pythonVersion": "3.11.11"
}
```

## Shell Config

The installer maintains a marked block in `~/.zshrc`:

```text
# >>> workspace managed >>>
...
# <<< workspace managed <<<
```

The block adds `~/.local/bin`, the repo `.venv/bin`, Spark 4 environment
variables, optional `kubectl`/`helm` completions, and locale defaults. It also
unsets `LC_ALL`; the installer generates `WORKSPACE_LOCALE` during the base apt
phase instead of forcing an unavailable locale in every shell.

Project-specific remote workstation aliases belong in the project-owned
workstation access helper, not in the generic Wielder installer. The managed
block intentionally keeps only reusable shell environment setup.

If `~/.zsh_secrets` exists, the managed shell block sources it. This is the
right place for local-only preferences such as:

```bash
export AWS_PROFILE=gid-cli-user-mfa
export AWS_PAGER=""
```

Do not place short-lived MFA session credentials in `.zshrc` or
`~/.zsh_secrets`; refresh those through the AWS CLI MFA profile or the
Wielder/Terraform helper when needed.

## Spark Contract

Wielder Spark helpers auto-detect Spark 4 under `~/opt` or from
`SPARK_HOME`/`SPARK4_HOME`/`PYSPARK_HOME`. The installer therefore places Spark
under `~/opt` and maintains `~/opt/spark-4` as a stable alias.

The Python package dependency remains `pyspark==4.0.1`; the physical Spark
runtime is installed separately because `spark-submit` and Java are runtime
tooling, not just Python package dependencies.
