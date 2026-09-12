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
  printf 'base=%s\n' "${ANTHROPIC_BASE_URL-<unset>}"
  printf 'model=%s\n' "${ANTHROPIC_MODEL-<unset>}"
  printf 'opus=%s\n' "${ANTHROPIC_DEFAULT_OPUS_MODEL-<unset>}"
  printf 'haiku=%s\n' "${ANTHROPIC_DEFAULT_HAIKU_MODEL-<unset>}"
  printf 'subagent=%s\n' "${CLAUDE_CODE_SUBAGENT_MODEL-<unset>}"
  printf 'config=%s\n' "${CLAUDE_CONFIG_DIR-<unset>}"
  printf 'api_key=%s\n' "${ANTHROPIC_API_KEY-<unset>}"
  if [[ -n "${ANTHROPIC_AUTH_TOKEN-}" ]]; then
    printf '%s\n' 'auth_token=present'
  else
    printf '%s\n' 'auth_token=missing'
  fi
  printf 'auto_compact=%s\n' "${CLAUDE_CODE_AUTO_COMPACT_WINDOW-<unset>}"
  printf 'effort=%s\n' "${CLAUDE_CODE_EFFORT_LEVEL-<unset>}"
  printf 'args='
  printf '<%s>' "$@"
  printf '\n'
} >"$CLAUDE_PROVIDER_TEST_OUTPUT"
SH
chmod 0700 "$fake_claude"

kimi_output="$test_root/kimi.out"
HOME="$fake_home" \
CLAUDE_PROVIDER_SECURITY_BIN="$fake_security" \
CLAUDE_PROVIDER_CLAUDE_BIN="$fake_claude" \
CLAUDE_PROVIDER_TEST_OUTPUT="$kimi_output" \
ANTHROPIC_BASE_URL="https://stale.example" \
ANTHROPIC_API_KEY="stale-api-key" \
ANTHROPIC_MODEL="stale-model" \
  "$script_dir/claude-kimi" -p test-prompt

rg -Fx 'base=https://api.moonshot.ai/anthropic' "$kimi_output" >/dev/null
rg -Fx 'model=kimi-k3[1m]' "$kimi_output" >/dev/null
rg -Fx 'opus=kimi-k3[1m]' "$kimi_output" >/dev/null
rg -Fx 'haiku=kimi-k2.7-code' "$kimi_output" >/dev/null
rg -Fx 'subagent=kimi-k3[1m]' "$kimi_output" >/dev/null
rg -Fx 'config=<unset>' "$kimi_output" >/dev/null
rg -Fx 'api_key=' "$kimi_output" >/dev/null
rg -Fx 'auth_token=present' "$kimi_output" >/dev/null
rg -Fx 'auto_compact=1000000' "$kimi_output" >/dev/null
rg -Fx 'effort=max' "$kimi_output" >/dev/null
rg -Fx 'args=<--dangerously-skip-permissions><--permission-mode><bypassPermissions><-p><test-prompt>' "$kimi_output" >/dev/null

missing_kimi_output="$test_root/missing-kimi.out"
if HOME="$fake_home" \
  CLAUDE_PROVIDER_TEST_CREDENTIAL_STATE=missing \
  CLAUDE_PROVIDER_SECURITY_BIN="$fake_security" \
  CLAUDE_PROVIDER_CLAUDE_BIN="$fake_claude" \
  CLAUDE_PROVIDER_TEST_OUTPUT="$missing_kimi_output" \
    "$script_dir/claude-kimi" >"$test_root/missing-kimi.stdout" 2>"$test_root/missing-kimi.stderr"; then
  printf '%s\n' 'Expected missing Kimi credential to fail' >&2
  exit 1
fi
test ! -e "$missing_kimi_output"

fake_curl="$test_root/fake-curl"
cat >"$fake_curl" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' '{"data":[{"id":"kimi-k3"}]}'
SH
chmod 0700 "$fake_curl"

install -d -m 0700 "$fake_home/cliproxyapi"
printf '%s' 'test-proxy-token' >"$fake_home/cliproxyapi/client-token"
chmod 0600 "$fake_home/cliproxyapi/client-token"

kimi_proxy_output="$test_root/kimi-proxy.out"
HOME="$fake_home" \
CLAUDE_PROVIDER_CLAUDE_BIN="$fake_claude" \
CLAUDE_KIMI_PROXY_CURL_BIN="$fake_curl" \
CLAUDE_PROVIDER_TEST_OUTPUT="$kimi_proxy_output" \
  "$script_dir/claude-kimi-proxy" -p test-prompt

rg -Fx 'base=http://127.0.0.1:8317' "$kimi_proxy_output" >/dev/null
rg -Fx 'model=kimi-k3(max)' "$kimi_proxy_output" >/dev/null
rg -Fx 'auth_token=present' "$kimi_proxy_output" >/dev/null
rg -Fx 'auto_compact=262144' "$kimi_proxy_output" >/dev/null
rg -Fx 'args=<--dangerously-skip-permissions><--permission-mode><bypassPermissions><--effort><max><-p><test-prompt>' "$kimi_proxy_output" >/dev/null

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
  "$script_dir/claude-provider-auth" kimi --status >"$auth_output"
rg -F 'provider=kimi' "$auth_output" >/dev/null

installer_home="$test_root/installer-home"
HOME="$installer_home" "$script_dir/install-claude-provider-launchers.sh" >/dev/null
for command_name in \
  claude-codex \
  claude-codex-high \
  claude-codex-xhigh \
  claude-kimi \
  claude-kimi-proxy \
  claude-provider \
  claude-provider-auth \
  claude-openrouter \
  claude-featherless; do
  test -x "$installer_home/.local/bin/$command_name"
done
test "$(readlink "$installer_home/.local/bin/claude-openrouter")" = "claude-provider"
test "$(readlink "$installer_home/.local/bin/claude-featherless")" = "claude-provider"
cmp "$installer_home/.local/bin/claude-kimi" "$script_dir/claude-kimi"
cmp "$installer_home/.local/bin/claude-kimi-proxy" "$script_dir/claude-kimi-proxy"

printf '%s\n' 'Claude provider route tests passed'
