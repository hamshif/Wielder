#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CURRENT_INSTALLER="${SCRIPT_DIR}/../wielder/scripts/install_ubuntu.sh"

cat <<EOF
[legacy] prepare_ubuntu.sh has been retired.

The old script mixed Perl/CPAN, pyenv, jenv, obsolete Spark, Lens, Terraform,
Docker, Helm, Kubernetes, and package installation in one broad mutation path.

Use the maintained Ubuntu/WSL installer instead:
  ${CURRENT_INSTALLER}

EOF

exit 1
