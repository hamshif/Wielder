#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cat <<EOF
[legacy] create_pyenv.bash has been retired.

Wielder/Workspace Ubuntu setup now uses uv and a repo-local .venv.

Use:
  ${SCRIPT_DIR}/install_ubuntu.sh

EOF

exit 1
