#!/usr/bin/env bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1

repo_root="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
package_root="${repo_root}/internal"
source_root="${CTX9_SOURCE_ROOT:-${repo_root}}"
home_dir="${HOME}"
machine_id="$(hostname -s 2>/dev/null | tr '[:upper:]_' '[:lower:]-' || printf primary)"
code_root="~/Developer"
vault_root=""
global_instructions=0
claude_alias=0

ask() {
  local prompt="$1"
  local default_value="$2"
  local answer=""
  printf '%s [%s]: ' "${prompt}" "${default_value}" >/dev/tty
  IFS= read -r answer </dev/tty || answer=""
  printf '%s' "${answer:-${default_value}}"
}

ask_yes() {
  local prompt="$1"
  local answer=""
  printf '%s [y/N] ' "${prompt}" >/dev/tty
  IFS= read -r answer </dev/tty || answer=""
  [[ "${answer}" =~ ^([yY]|yes|YES)$ ]]
}

if [[ -r /dev/tty && "${CTX9_NON_INTERACTIVE:-0}" != "1" ]]; then
  machine_id="$(ask 'Machine name' "${machine_id}")"
  code_root="$(ask 'Code root' "${code_root}")"
  if ask_yes 'Connect this install to a local Context Vault?'; then
    vault_root="$(ask 'Vault path' "~/Vault")"
  fi
  if ask_yes 'Generate managed global agent instructions?'; then
    global_instructions=1
    if ask_yes 'Create the Claude instruction alias?'; then
      claude_alias=1
    fi
  fi
fi

args=(
  "${package_root}/src/fleet.py" install
  --source "${source_root}"
  --home "${home_dir}"
  --machine-id "${machine_id}"
  --code-root "${code_root}"
  --initialize-source
  --discovery-aliases
  --apply
)
[[ -n "${vault_root}" ]] && args+=(--vault-root "${vault_root}")
[[ "${global_instructions}" == "1" ]] && args+=(--global-instructions)
[[ "${claude_alias}" == "1" ]] && args+=(--claude-alias)

python3 "${args[@]}"
python3 "${package_root}/src/fleet.py" config validate --config-root "${home_dir}/.agents/settings"
python3 "${package_root}/src/fleet.py" verify --home "${home_dir}"

printf '\nInstalled fleet and all public skills.\n'
printf 'Editable source: %s/edit\n' "${source_root}"
printf 'This repository has no user remote until you add one.\n'
