#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "" || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  cat <<'EOF'
Usage:
  debug_python_entrypoint.sh <python-entrypoint> [entrypoint args...]

Environment:
  DEBUGPY_HOST            Debug host to bind. Default: 127.0.0.1
  DEBUGPY_PORT            Debug port to bind. Default: 5678
  DEBUGPY_WAIT_FOR_CLIENT Wait for debugger attach before running.
                          Default: 1
  PYTHON_BIN              Python executable to use. Default: python

Example:
  <workspace>/Wielder/wielder/scripts/debug_python_entrypoint.sh \
    <workspace>/workflow-wielder/src/workspace_wielder/deploy/apps/model_binding_workflow/wield/model_binding_workflow_deploy.py \
    -es kind_gpu_model_binding -st dev -w apply
EOF
  exit 0
fi

entrypoint="$1"
shift

host="${DEBUGPY_HOST:-127.0.0.1}"
port="${DEBUGPY_PORT:-5678}"
wait_for_client="${DEBUGPY_WAIT_FOR_CLIENT:-1}"
python_bin="${PYTHON_BIN:-python}"

if [[ ! -f "$entrypoint" ]]; then
  echo "debug_python_entrypoint.sh: entrypoint not found: $entrypoint" >&2
  exit 1
fi

if ! "$python_bin" -c "import debugpy" >/dev/null 2>&1; then
  echo "debug_python_entrypoint.sh: debugpy is not installed for [$python_bin]" >&2
  exit 1
fi

export DEBUGPY_WRAPPER_HOST="$host"
export DEBUGPY_WRAPPER_PORT="$port"
export DEBUGPY_WRAPPER_WAIT="$wait_for_client"

exec "$python_bin" -Xfrozen_modules=off -c '
import os
import runpy
import sys

import debugpy

entrypoint = sys.argv[1]
forwarded_args = sys.argv[2:]
host = os.environ["DEBUGPY_WRAPPER_HOST"]
port = int(os.environ["DEBUGPY_WRAPPER_PORT"])
wait_for_client = os.environ["DEBUGPY_WRAPPER_WAIT"] != "0"

debugpy.listen((host, port))
print(f"debugpy listening on {host}:{port}", flush=True)
print(f"entrypoint: {entrypoint}", flush=True)
print("args: " + " ".join(forwarded_args), flush=True)

if wait_for_client:
    print(f"waiting for debugger attach on {host}:{port} before starting entrypoint", flush=True)
    debugpy.wait_for_client()

sys.argv = [entrypoint] + forwarded_args
runpy.run_path(entrypoint, run_name="__main__")
' "$entrypoint" "$@"
