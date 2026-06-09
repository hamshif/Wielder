#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
debug_wrapper="${script_dir}/debug_python_entrypoint.sh"

if [[ ! -f "$debug_wrapper" ]]; then
  echo "install_wildebug.sh: debug wrapper not found: $debug_wrapper" >&2
  exit 1
fi

shell_name="${SHELL##*/}"
rc_file=""

case "$shell_name" in
  zsh)
    rc_file="${HOME}/.zshrc"
    ;;
  bash)
    rc_file="${HOME}/.bashrc"
    ;;
  *)
    rc_file="${HOME}/.zshrc"
    echo "install_wildebug.sh: unsupported shell [$shell_name], defaulting to [$rc_file]" >&2
    ;;
esac

alias_line="alias wildebug='${debug_wrapper}'"

touch "$rc_file"

if grep -Fqx "$alias_line" "$rc_file"; then
  echo "wildebug alias already installed in ${rc_file}"
  exit 0
fi

{
  echo
  echo "# Wielder terminal debug wrapper"
  echo "$alias_line"
} >> "$rc_file"

echo "Installed wildebug alias in ${rc_file}"
echo "Reload your shell or run: source ${rc_file}"
