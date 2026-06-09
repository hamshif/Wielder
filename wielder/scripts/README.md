# Wielder Scripts

Short index for the operator-facing scripts under [wielder/scripts](<workspace>/Wielder/wielder/scripts).

## Installers

- [install_ubuntu.sh](<workspace>/Wielder/wielder/scripts/install_ubuntu.sh)
  Consolidated Ubuntu/WSL workstation installer. Uses `uv`, a repo-local `.venv`,
  Java 17, Spark 4, cloud CLIs, Terraform, `kubectl`, Helm, and optional delegated
  Docker/GPU/kind/Azure phases.

- [install_docker_wsl_ubuntu.sh](<workspace>/Wielder/wielder/scripts/install_docker_wsl_ubuntu.sh)
  Install Docker CE inside WSL Ubuntu and enable the Docker daemon.

- [install_nvidia_container_toolkit_wsl_ubuntu.sh](<workspace>/Wielder/wielder/scripts/install_nvidia_container_toolkit_wsl_ubuntu.sh)
  Install the NVIDIA Container Toolkit and verify direct and nested GPU container access.

- [install_local_gpu_container_stack_wsl_ubuntu.sh](<workspace>/Wielder/wielder/scripts/install_local_gpu_container_stack_wsl_ubuntu.sh)
  Run the Docker and NVIDIA installer chain for local GPU containers on WSL.

- [reinstall_local_gpu_container_stack_wsl_ubuntu.sh](<workspace>/Wielder/wielder/scripts/reinstall_local_gpu_container_stack_wsl_ubuntu.sh)
  Force-reinstall the local GPU container stack when the Docker or NVIDIA surface has drifted.

- [install_k3d_wsl_ubuntu.sh](<workspace>/Wielder/wielder/scripts/install_k3d_wsl_ubuntu.sh)
  Install `k3d` in WSL Ubuntu.

- [install_kind_wsl_ubuntu.sh](<workspace>/Wielder/wielder/scripts/install_kind_wsl_ubuntu.sh)
  Install plain `kind` in WSL Ubuntu and create a non-GPU cluster with local mounts and host port mappings.

- [install_kind_gpu_wsl_ubuntu.sh](<workspace>/Wielder/wielder/scripts/install_kind_gpu_wsl_ubuntu.sh)
  Install and configure the GPU-capable `kind` surface used for local GPU Kubernetes validation.

- [install_visualizer_wsl_ubuntu.sh](<workspace>/Wielder/wielder/scripts/install_visualizer_wsl_ubuntu.sh)
  Install Graphviz and local report-opening helpers in WSL Ubuntu, and install VS Code Mermaid/Graphviz preview extensions when the `code` CLI is available.

- [install_azure_cli_wsl_ubuntu.sh](<workspace>/Wielder/wielder/scripts/install_azure_cli_wsl_ubuntu.sh)
  Install Microsoft Azure CLI in WSL Ubuntu for tenant-scoped Microsoft Graph and SharePoint access flows.

## Helpers

- [compact_wsl_vhd.ps1](<workspace>/Wielder/wielder/scripts/compact_wsl_vhd.ps1)
  Windows-side companion for reclaiming WSL VHDX space after heavy Docker or cluster churn. Run it from an elevated PowerShell session after Linux-side cleanup.
  Example:
  `& "$HOME\\workspace\\Wielder\\wielder\\scripts\\compact_wsl_vhd.ps1" -DistroName Ubuntu`

- [install_apt_helpers.sh](<workspace>/Wielder/wielder/scripts/install_apt_helpers.sh)
  Shared apt lock-wait helpers used by the installer scripts.

- [debug_python_entrypoint.sh](<workspace>/Wielder/wielder/scripts/debug_python_entrypoint.sh)
  Wrap a Python entrypoint with `debugpy` for local debugging.

- [legacy_create_pyenv.bash](<workspace>/Wielder/wielder/scripts/legacy_create_pyenv.bash)
  Legacy guard for the retired pyenv environment creator. Use `install_ubuntu.sh`.

- [uvenv.sh](<workspace>/Wielder/wielder/scripts/uvenv.sh)
  Sourceable bash/zsh helpers for activating, creating, listing, and
  deactivating `uv` virtual environments.

- [is_docker_running.sh](<workspace>/Wielder/wielder/scripts/is_docker_running.sh)
  Small probe to check whether the Docker daemon is reachable.

- [install_wildebug.sh](<workspace>/Wielder/wielder/scripts/install_wildebug.sh)
  Install the lightweight `wildebug` helper.

- [wield_git.py](<workspace>/Wielder/wielder/scripts/wield_git.py)
  Git helper entrypoint owned by `Wielder`.
