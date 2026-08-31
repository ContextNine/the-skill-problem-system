#!/usr/bin/env bash
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
target_dir="$HOME/.local/bin"

if [[ $# -gt 1 ]]; then
  printf '%s\n' "Usage: $0 [ssh-alias]" >&2
  exit 2
fi

if [[ $# -eq 1 ]]; then
  ssh_alias="$1"
  remote_dir=$(ssh "$ssh_alias" 'mktemp -d')
  case "$remote_dir" in
    /tmp/tmp.*|/var/folders/*/*/T/tmp.*)
      ;;
    *)
      printf '%s\n' "Unexpected remote temporary directory: $remote_dir" >&2
      exit 1
      ;;
  esac

  scp \
    "$script_dir/claude-codex" \
    "$script_dir/claude-kimi" \
    "$script_dir/install-claude-provider-launchers.sh" \
    "$ssh_alias:$remote_dir/"
  ssh "$ssh_alias" \
    "chmod 0700 '$remote_dir/claude-codex' '$remote_dir/claude-kimi' '$remote_dir/install-claude-provider-launchers.sh'; '$remote_dir/install-claude-provider-launchers.sh'; rm -r -- '$remote_dir'"
  exit
fi

install -d -m 0700 "$target_dir"
install -m 0700 "$script_dir/claude-codex" "$target_dir/claude-codex"
install -m 0700 "$script_dir/claude-kimi" "$target_dir/claude-kimi"
ln -sfn claude-codex "$target_dir/claude-codex-high"
ln -sfn claude-codex "$target_dir/claude-codex-xhigh"

for command_name in claude-codex claude-codex-high claude-codex-xhigh claude-kimi; do
  test -x "$target_dir/$command_name"
done

printf 'Installed Claude provider launchers in %s\n' "$target_dir"
