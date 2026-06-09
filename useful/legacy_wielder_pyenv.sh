#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CURRENT_INSTALLER="${SCRIPT_DIR}/../wielder/scripts/install_ubuntu.sh"

cat <<EOF
[legacy] wielder_pyenv.sh has been retired.

Workspace Ubuntu/WSL environments now use uv and a repo-local .venv instead of
pyenv virtualenvs.

Use:
  ${CURRENT_INSTALLER}

EOF

exit 1
