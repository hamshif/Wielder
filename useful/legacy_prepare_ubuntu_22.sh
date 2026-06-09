#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CURRENT_INSTALLER="${SCRIPT_DIR}/../wielder/scripts/install_ubuntu.sh"

cat <<EOF
[legacy] prepare_ubuntu_22.sh has been retired.

It used pyenv/jenv and older Java/Spark assumptions. The current Ubuntu path is
uv-based and lives here:
  ${CURRENT_INSTALLER}

EOF

exit 1
