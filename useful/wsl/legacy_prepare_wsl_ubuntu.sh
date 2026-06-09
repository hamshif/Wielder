#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CURRENT_INSTALLER="${SCRIPT_DIR}/../../wielder/scripts/install_ubuntu.sh"

cat <<EOF
[legacy] prepare_wsl_ubuntu.sh has been retired.

The old WSL script used pyenv/jenv and Spark 3 era setup. The maintained WSL
Ubuntu installer is:
  ${CURRENT_INSTALLER}

EOF

exit 1
