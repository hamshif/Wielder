#!/usr/bin/env bash
set -euo pipefail

sudo_safe() {
  if [[ -t 0 && -t 1 ]]; then
    sudo "$@"
  else
    sudo -n "$@"
  fi
}

wait_for_apt_locks() {
  local waited=0
  while sudo_safe fuser /var/lib/apt/lists/lock >/dev/null 2>&1 \
    || sudo_safe fuser /var/cache/apt/archives/lock >/dev/null 2>&1 \
    || sudo_safe fuser /var/lib/dpkg/lock >/dev/null 2>&1 \
    || sudo_safe fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1; do
    printf '[install-apt] Waiting for apt/dpkg lock (%ss)\n' "${waited}" >&2
    sleep 2
    waited=$((waited + 2))
  done
}

apt_get_safe() {
  wait_for_apt_locks
  sudo_safe apt-get "$@"
}
