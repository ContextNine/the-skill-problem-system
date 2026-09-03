#!/usr/bin/env bash
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
test_root="$(mktemp -d "${TMPDIR:-/tmp}/ctx9-claude-provider-test.XXXXXX")"
case "$test_root" in
  "${TMPDIR:-/tmp}"/ctx9-claude-provider-test.*)
    ;;
  *)
    printf '%s\n' "Unexpected test directory: $test_root" >&2
    exit 1
    ;;
esac

cleanup() {
  case "$test_root" in
    "${TMPDIR:-/tmp}"/ctx9-claude-provider-test.*)
      rm -rf -- "$test_root"
      ;;
  esac
}
trap cleanup EXIT HUP INT TERM

fake_home="$test_root/home"
fake_bin="$test_root/bin"
install -d -m 0700 "$fake_home/.local/bin" "$fake_home/.claude" "$fake_bin"

fake_security="$fake_bin/security"
cat >"$fake_security" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
case "${1-}" in
  find-generic-password)
    if [[ "${CLAUDE_PROVIDER_TEST_CREDENTIAL_STATE:-present}" == "present" ]]; then
      if [[ " $* " == *" -w "* ]]; then
        printf '%s' 'test-provider-key'
      fi
      exit 0
    fi
    exit 44
    ;;
  add-generic-password)
    exit 0
    ;;
esac
exit 2
SH
chmod 0700 "$fake_security"

fake_claude="$fake_bin/claude"
cat >"$fake_claude" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
test -n "${CLAUDE_PROVIDER_TEST_OUTPUT:-}"
{
  printf 'base=%s\n' "$ANTHROPIC_BASE_URL"
  printf 'model=%s\n' "$ANTHROPIC_MODEL"
  printf 'opus=%s\n' "$ANTHROPIC_DEFAULT_OPUS_MODEL"
  printf 'subagent=%s\n' "$CLAUDE_CODE_SUBAGENT_MODEL"
  printf 'config=%s\n' "$CLAUDE_CONFIG_DIR"
  printf 'api_key=%s\n' "$ANTHROPIC_API_KEY"
  printf 'args='
  printf '<%s>' "$@"
  printf '\n'
} >"$CLAUDE_PROVIDER_TEST_OUTPUT"
SH
chmod 0700 "$fake_claude"

ln -s "$script_dir/claude-provider" "$fake_bin/claude-openrouter"
ln -s "$script_dir/claude-provider" "$fake_bin/claude-featherless"

openrouter_output="$test_root/openrouter.out"
HOME="$fake_home" \
XDG_CONFIG_HOME="$fake_home/.config" \
CLAUDE_PROVIDER_SECURITY_BIN="$fake_security" \
CLAUDE_PROVIDER_CLAUDE_BIN="$fake_claude" \
CLAUDE_PROVIDER_TEST_OUTPUT="$openrouter_output" \
  "$fake_bin/claude-openrouter" moonshotai/kimi-k3 -p test-prompt

rg -Fx 'base=https://openrouter.ai/api' "$openrouter_output" >/dev/null
rg -Fx 'model=moonshotai/kimi-k3' "$openrouter_output" >/dev/null
rg -Fx 'opus=moonshotai/kimi-k3' "$openrouter_output" >/dev/null
rg -Fx 'subagent=moonshotai/kimi-k3' "$openrouter_output" >/dev/null
rg -Fx "config=$fake_home/.config/ctx9/claude-provider-routes/claude/openrouter" "$openrouter_output" >/dev/null
rg -Fx 'api_key=' "$openrouter_output" >/dev/null
rg -Fx 'args=<--dangerously-skip-permissions><--permission-mode><bypassPermissions><-p><test-prompt>' "$openrouter_output" >/dev/null

missing_output="$test_root/missing.out"
if HOME="$fake_home" \
  CLAUDE_PROVIDER_TEST_CREDENTIAL_STATE=missing \
  CLAUDE_PROVIDER_SECURITY_BIN="$fake_security" \
  CLAUDE_PROVIDER_CLAUDE_BIN="$fake_claude" \
  CLAUDE_PROVIDER_TEST_OUTPUT="$missing_output" \
    "$fake_bin/claude-openrouter" moonshotai/kimi-k3 >"$test_root/missing.stdout" 2>"$test_root/missing.stderr"; then
  printf '%s\n' 'Expected missing OpenRouter credential to fail' >&2
  exit 1
fi
test ! -e "$missing_output"

proxy_bin="${CLAUDE_PROVIDER_PROXY_BIN:-$HOME/cliproxyapi/current/cli-proxy-api}"
if [[ ! -x "$proxy_bin" ]]; then
  printf '%s\n' "Missing CLIProxyAPI test dependency: $proxy_bin" >&2
  exit 1
fi

featherless_output="$test_root/featherless.out"
HOME="$fake_home" \
XDG_CONFIG_HOME="$fake_home/.config" \
CLAUDE_PROVIDER_SECURITY_BIN="$fake_security" \
CLAUDE_PROVIDER_CLAUDE_BIN="$fake_claude" \
CLAUDE_PROVIDER_PROXY_BIN="$proxy_bin" \
CLAUDE_PROVIDER_TEST_OUTPUT="$featherless_output" \
  "$fake_bin/claude-featherless" empero-ai/Qwythos-9B-Claude-Mythos-5-1M --model ignored-by-launcher

rg '^base=http://127\.0\.0\.1:[0-9]+$' "$featherless_output" >/dev/null
rg -Fx 'model=empero-ai/Qwythos-9B-Claude-Mythos-5-1M' "$featherless_output" >/dev/null
rg -Fx "config=$fake_home/.config/ctx9/claude-provider-routes/claude/featherless" "$featherless_output" >/dev/null
rg -Fx 'args=<--dangerously-skip-permissions><--permission-mode><bypassPermissions><--model><ignored-by-launcher>' "$featherless_output" >/dev/null

auth_output="$test_root/auth.out"
HOME="$fake_home" \
CLAUDE_PROVIDER_SECURITY_BIN="$fake_security" \
  "$script_dir/claude-provider-auth" openrouter --status >"$auth_output"
rg -F 'provider=openrouter' "$auth_output" >/dev/null

installer_home="$test_root/installer-home"
HOME="$installer_home" "$script_dir/install-claude-provider-launchers.sh" >/dev/null
for command_name in \
  claude-codex \
  claude-codex-high \
  claude-codex-xhigh \
  claude-kimi \
  claude-provider \
  claude-provider-auth \
  claude-openrouter \
  claude-featherless; do
  test -x "$installer_home/.local/bin/$command_name"
done
test "$(readlink "$installer_home/.local/bin/claude-openrouter")" = "claude-provider"
test "$(readlink "$installer_home/.local/bin/claude-featherless")" = "claude-provider"

printf '%s\n' 'Claude provider route tests passed'
