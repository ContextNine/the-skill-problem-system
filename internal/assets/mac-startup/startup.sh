#!/bin/zsh

set -euo pipefail

remap_tilde_key() {
  local mapping='{"UserKeyMapping":[{"HIDKeyboardModifierMappingSrc":0x700000035,"HIDKeyboardModifierMappingDst":0x700000064}]}'
  /usr/bin/hidutil property --set "$mapping"
  echo "Applied remap-tilde-key at $(/bin/date '+%Y-%m-%d %H:%M:%S')"
}

open_application() {
  local bundle_id="$1"
  /usr/bin/open -gj -b "$bundle_id"
  echo "Opened $bundle_id at $(/bin/date '+%Y-%m-%d %H:%M:%S')"
}

run_action() {
  case "$1" in
    remap-tilde-key)
      remap_tilde_key
      ;;
    open-application:*)
      open_application "${1#open-application:}"
      ;;
    *)
      echo "Unknown mac-startup action: $1" >&2
      return 2
      ;;
  esac
}

if (( $# == 0 )); then
  echo "No mac-startup actions were provided." >&2
  exit 2
fi

for action in "$@"; do
  run_action "$action"
done
