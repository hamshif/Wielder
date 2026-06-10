# shellcheck shell=bash
# Source this file from bash or zsh to get pyenv-like helpers for uv venvs.

_uvenv_home() {
  printf '%s\n' "${UVENV_HOME:-${HOME}/.uvenvs}"
}

_uvenv_default() {
  printf '%s\n' "${UVENV_DEFAULT_VENV:-.venv}"
}

_uvenv_default_name() {
  printf '%s\n' "${UVENV_DEFAULT_NAME:-}"
}

_uvenv_registry_file() {
  printf '%s/.uvenv-names\n' "$(_uvenv_home)"
}

_uvenv_registry_lookup() {
  local requested="$1" registry line name path
  registry="$(_uvenv_registry_file)"
  [[ -n "$requested" && -f "$registry" ]] || return 1

  while IFS= read -r line || [[ -n "$line" ]]; do
    case "$line" in
      ""|\#*) continue ;;
    esac
    name="${line%%=*}"
    path="${line#*=}"
    if [[ "$name" == "$requested" && "$path" != "$line" && -n "$path" ]]; then
      printf '%s\n' "$path"
      return 0
    fi
  done < "$registry"

  return 1
}

_uvenv_registry_name_for_path() {
  local requested="$1" registry line name path resolved
  registry="$(_uvenv_registry_file)"
  [[ -n "$requested" && -f "$registry" ]] || return 1

  while IFS= read -r line || [[ -n "$line" ]]; do
    case "$line" in
      ""|\#*) continue ;;
    esac
    name="${line%%=*}"
    path="${line#*=}"
    [[ -n "$name" && "$path" != "$line" && -n "$path" ]] || continue
    resolved="$(_uvenv_make_absolute "$path")"
    if [[ "$resolved" == "$requested" ]]; then
      printf '%s\n' "$name"
      return 0
    fi
  done < "$registry"

  return 1
}

_uvenv_python_version() {
  printf '%s\n' "${UVENV_PYTHON_VERSION:-3.11.11}"
}

_uvenv_is_pathlike() {
  case "$1" in
    /*|*/*|.|..|.*) return 0 ;;
    *) return 1 ;;
  esac
}

_uvenv_make_absolute() {
  local requested="$1"
  case "$requested" in
    /*) printf '%s\n' "$requested" ;;
    *) printf '%s/%s\n' "$PWD" "$requested" ;;
  esac
}

_uvenv_resolve() {
  local requested="${1:-$(_uvenv_default)}"
  local mode="${2:-activate}"
  local home_dir default_name
  home_dir="$(_uvenv_home)"
  default_name="$(_uvenv_default_name)"

  if [[ -n "$default_name" && "$requested" == "$default_name" ]]; then
    requested="$(_uvenv_default)"
  fi

  if ! _uvenv_is_pathlike "$requested"; then
    local registered
    registered="$(_uvenv_registry_lookup "$requested")" && {
      _uvenv_make_absolute "$registered"
      return
    }
  fi

  if [[ "$requested" == */bin/activate ]]; then
    requested="${requested%/bin/activate}"
    _uvenv_make_absolute "$requested"
    return
  fi

  if _uvenv_is_pathlike "$requested"; then
    _uvenv_make_absolute "$requested"
    return
  fi

  if [[ -f "$PWD/$requested/bin/activate" ]]; then
    printf '%s/%s\n' "$PWD" "$requested"
  elif [[ -f "$PWD/.$requested/bin/activate" ]]; then
    printf '%s/.%s\n' "$PWD" "$requested"
  elif [[ -f "$home_dir/$requested/bin/activate" || "$mode" == "create" ]]; then
    printf '%s/%s\n' "$home_dir" "$requested"
  else
    printf '%s/%s\n' "$home_dir" "$requested"
  fi
}

_uvenv_display_name() {
  local requested="${1:-}" venv_path="${2:-}" default_name default_path home_dir registry_name
  default_name="$(_uvenv_default_name)"
  default_path="$(_uvenv_resolve "$(_uvenv_default)" activate)"
  home_dir="$(_uvenv_home)"
  registry_name="$(_uvenv_registry_name_for_path "$venv_path" 2>/dev/null)" || registry_name=""

  if [[ -n "$default_name" && "$requested" == "$default_name" ]]; then
    printf '%s\n' "$default_name"
  elif [[ -n "$default_name" && "$venv_path" == "$default_path" ]]; then
    printf '%s\n' "$default_name"
  elif [[ -n "$registry_name" ]]; then
    printf '%s\n' "$registry_name"
  elif [[ "$venv_path" == "$home_dir/"* ]]; then
    basename "$venv_path"
  else
    basename "$venv_path"
  fi
}

_uvenv_ensure_uv() {
  local uv_dir
  if command -v uv >/dev/null 2>&1; then
    return 0
  fi

  for uv_dir in "$HOME/.local/bin" "$HOME/.cargo/bin"; do
    if [[ -x "$uv_dir/uv" ]]; then
      export PATH="$uv_dir:$PATH"
      command -v uv >/dev/null 2>&1 && return 0
    fi
  done

  printf 'uvenv: uv command not found. Install uv or add it to PATH.\n' >&2
  return 1
}

_uvenv_has_python_arg() {
  local arg
  for arg in "$@"; do
    case "$arg" in
      --python|--python=*) return 0 ;;
    esac
  done
  return 1
}

_uvenv_has_existing_policy_arg() {
  local arg
  for arg in "$@"; do
    case "$arg" in
      --allow-existing|--clear|--force) return 0 ;;
    esac
  done
  return 1
}

_uvenv_has_seed_arg() {
  local arg
  for arg in "$@"; do
    case "$arg" in
      --seed) return 0 ;;
    esac
  done
  return 1
}

_uvenv_is_python_version_arg() {
  [[ "${1:-}" =~ ^[0-9]+(\.[0-9]+){1,2}$ ]]
}

uvenv-activate() {
  local requested venv_path activate_script
  requested="${1:-}"
  venv_path="$(_uvenv_resolve "$requested" activate)" || return 1
  activate_script="$venv_path/bin/activate"

  if [[ ! -f "$activate_script" ]]; then
    printf 'uvenv: missing virtualenv activation script: %s\n' "$activate_script" >&2
    printf 'Create it with: uvenv create %s\n' "$venv_path" >&2
    return 1
  fi

  export VIRTUAL_ENV_DISABLE_PROMPT=1
  # shellcheck disable=SC1090
  source "$activate_script"
  export UVENV_ACTIVE_NAME="$(_uvenv_display_name "$requested" "$venv_path")"
}

uvenv-deactivate() {
  if typeset -f deactivate >/dev/null 2>&1; then
    deactivate
    unset UVENV_ACTIVE_NAME
    return
  fi

  printf 'uvenv: no active Python virtual environment was found.\n' >&2
  return 1
}

uvenv-create() {
  local target="${UVENV_DEFAULT_VENV:-.venv}"
  local venv_path python_version
  local uv_args=()

  if (($# > 0)) && [[ "$1" != -* ]]; then
    target="$1"
    shift
  fi

  venv_path="$(_uvenv_resolve "$target" create)" || return 1
  mkdir -p "$(dirname "$venv_path")"
  _uvenv_ensure_uv || return 1

  if ! _uvenv_has_python_arg "$@" && _uvenv_is_python_version_arg "${1:-}"; then
    python_version="$1"
    shift
  fi

  uv_args=("$@")
  if ! _uvenv_has_existing_policy_arg "${uv_args[@]}"; then
    uv_args=(--allow-existing "${uv_args[@]}")
  fi
  if ! _uvenv_has_seed_arg "${uv_args[@]}"; then
    uv_args=(--seed "${uv_args[@]}")
  fi

  if _uvenv_has_python_arg "${uv_args[@]}"; then
    uv venv "${uv_args[@]}" "$venv_path"
  elif [[ -n "${python_version:-}" ]]; then
    uv venv --python "$python_version" "${uv_args[@]}" "$venv_path"
  else
    uv venv --python "$(_uvenv_python_version)" "${uv_args[@]}" "$venv_path"
  fi
}

uvenv-delete() {
  local target="${1:-}" venv_path
  if [[ -z "$target" ]]; then
    printf 'uvenv: delete requires an explicit path-or-name.\n' >&2
    return 1
  fi

  venv_path="$(_uvenv_resolve "$target" activate)" || return 1
  case "$venv_path" in
    ""|"/"|"$HOME"|"$PWD")
      printf 'uvenv: refusing to delete unsafe path: %s\n' "$venv_path" >&2
      return 1
      ;;
  esac

  if [[ ! -f "$venv_path/pyvenv.cfg" || ! -f "$venv_path/bin/activate" ]]; then
    printf 'uvenv: refusing to delete non-virtualenv path: %s\n' "$venv_path" >&2
    return 1
  fi

  if [[ "${VIRTUAL_ENV:-}" == "$venv_path" ]]; then
    uvenv-deactivate || true
  fi
  rm -rf -- "$venv_path"
}

uvenv-current() {
  if [[ -n "${VIRTUAL_ENV:-}" ]]; then
    printf '%s\n' "$VIRTUAL_ENV"
    return
  fi

  printf 'uvenv: no active Python virtual environment was found.\n' >&2
  return 1
}

uvenv-path() {
  _uvenv_resolve "${1:-}" activate
}

_uvenv_list_entry() {
  local candidate="$1" marker=" " name
  [[ -f "$candidate/bin/activate" ]] || return 0
  if [[ "$candidate" == "${VIRTUAL_ENV:-}" ]]; then
    marker="*"
  fi
  name="$(_uvenv_display_name "" "$candidate")"
  printf '%s %-24s %s\n' "$marker" "$name" "$candidate"
}

uvenv-list() {
  local candidate home_dir seen registry line name path
  home_dir="$(_uvenv_home)"
  registry="$(_uvenv_registry_file)"
  seen=":"

  for candidate in "${VIRTUAL_ENV:-}" "${UVENV_DEFAULT_VENV:-}" "$PWD/.venv" "$PWD/venv"; do
    [[ -n "$candidate" && -f "$candidate/bin/activate" ]] || continue
    candidate="$(_uvenv_resolve "$candidate" activate)"
    case "$seen" in
      *":$candidate:"*) continue ;;
    esac
    seen="${seen}${candidate}:"
    _uvenv_list_entry "$candidate"
  done

  if [[ -f "$registry" ]]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
      case "$line" in
        ""|\#*) continue ;;
      esac
      name="${line%%=*}"
      path="${line#*=}"
      [[ -n "$name" && "$path" != "$line" && -n "$path" ]] || continue
      candidate="$(_uvenv_make_absolute "$path")"
      [[ -f "$candidate/bin/activate" ]] || continue
      case "$seen" in
        *":$candidate:"*) continue ;;
      esac
      seen="${seen}${candidate}:"
      _uvenv_list_entry "$candidate"
    done < "$registry"
  fi

  if [[ -d "$home_dir" ]]; then
    while IFS= read -r candidate; do
      [[ -f "$candidate/bin/activate" ]] || continue
      case "$seen" in
        *":$candidate:"*) continue ;;
      esac
      seen="${seen}${candidate}:"
      _uvenv_list_entry "$candidate"
    done < <(find "$home_dir" -mindepth 1 -maxdepth 1 -type d 2>/dev/null)
  fi
}

uvenv-names() {
  local home_dir default_name registry line name candidate seen
  home_dir="$(_uvenv_home)"
  default_name="$(_uvenv_default_name)"
  registry="$(_uvenv_registry_file)"
  seen=":"

  if [[ -n "$default_name" ]]; then
    printf '%s\n' "$default_name"
    seen="${seen}${default_name}:"
  fi
  if [[ -f "$registry" ]]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
      case "$line" in
        ""|\#*) continue ;;
      esac
      name="${line%%=*}"
      [[ -n "$name" && "$name" != "$line" ]] || continue
      case "$seen" in
        *":$name:"*) continue ;;
      esac
      printf '%s\n' "$name"
      seen="${seen}${name}:"
    done < "$registry"
  fi
  if [[ -d "$home_dir" ]]; then
    while IFS= read -r candidate; do
      [[ -f "$candidate/bin/activate" ]] || continue
      name="$(basename "$candidate")"
      case "$seen" in
        *":$name:"*) continue ;;
      esac
      printf '%s\n' "$name"
      seen="${seen}${name}:"
    done < <(find "$home_dir" -mindepth 1 -maxdepth 1 -type d 2>/dev/null)
  fi
}

uvenv-help() {
  cat <<'EOF'
uvenv: pyenv-like helpers for uv-created virtualenvs

Usage:
  uvenv activate [path-or-name]
  uvenv switch [path-or-name]
  uvenv deactivate
  uvenv create [path-or-name] [python-version] [uv venv args...]
  uvenv delete [path-or-name]
  uvenv current
  uvenv path [path-or-name]
  uvenv list
  uvenv virtualenvs
  uvenv names

Shortcuts:
  uvenv-activate [path-or-name]
  uvenv-deactivate
  uv-activate [path-or-name]
  uv-deactivate
EOF
}

uvenv() {
  local command="${1:-activate}"

  case "$command" in
    activate|a|use)
      (($# > 0)) && shift
      uvenv-activate "$@"
      ;;
    switch|sw)
      (($# > 0)) && shift
      uvenv-activate "$@"
      ;;
    deactivate|d|off)
      (($# > 0)) && shift
      uvenv-deactivate "$@"
      ;;
    create|new|mk)
      (($# > 0)) && shift
      uvenv-create "$@"
      ;;
    delete|rm|remove)
      (($# > 0)) && shift
      uvenv-delete "$@"
      ;;
    current|which)
      (($# > 0)) && shift
      uvenv-current "$@"
      ;;
    path|resolve)
      (($# > 0)) && shift
      uvenv-path "$@"
      ;;
    list|ls)
      (($# > 0)) && shift
      uvenv-list "$@"
      ;;
    virtualenvs|venvs)
      (($# > 0)) && shift
      uvenv-list "$@"
      ;;
    names)
      (($# > 0)) && shift
      uvenv-names "$@"
      ;;
    help|-h|--help)
      uvenv-help
      ;;
    *)
      uvenv-activate "$@"
      ;;
  esac
}

uv-activate() {
  uvenv-activate "$@"
}

uv-deactivate() {
  uvenv-deactivate "$@"
}

if [[ -n "${ZSH_VERSION:-}" ]] && typeset -f compdef >/dev/null 2>&1; then
  _uvenv_zsh_complete() {
    local -a commands names
    commands=(activate switch deactivate create delete current path list virtualenvs help)
    names=($(uvenv-names 2>/dev/null))
    if (( CURRENT == 2 )); then
      compadd -- "${commands[@]}"
    else
      case "${words[2]}" in
        activate|switch|use|a|sw|delete|rm|remove|path|resolve)
          compadd -- "${names[@]}"
          ;;
      esac
    fi
  }
  compdef _uvenv_zsh_complete uvenv uvenv-activate uv-activate
fi
