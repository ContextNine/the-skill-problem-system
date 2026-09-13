#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=shlink-links-lib.sh
source "$SCRIPT_DIR/shlink-links-lib.sh"

PASS_COUNT=0

pass() {
    PASS_COUNT=$((PASS_COUNT + 1))
}

assert_pass() {
    "$@" >/dev/null 2>&1 || { echo "FAIL: expected success: $*" >&2; exit 1; }
    pass
}

assert_fail() {
    if "$@" >/dev/null 2>&1; then
        echo "FAIL: expected failure: $*" >&2
        exit 1
    fi
    pass
}

assert_equal() {
    local expected="$1"
    local actual="$2"
    [ "$actual" = "$expected" ] || { printf 'FAIL: expected <%s>, got <%s>\n' "$expected" "$actual" >&2; exit 1; }
    pass
}

assert_pass shlink_validate_slug launch
assert_pass shlink_validate_slug product-launch-2
assert_fail shlink_validate_slug Product-Launch
assert_fail shlink_validate_slug product_launch
assert_fail shlink_validate_slug product.launch
assert_fail shlink_validate_slug product--launch

assert_pass shlink_validate_utm_value --campaign product_launch_2
assert_fail shlink_validate_utm_value --campaign product-launch
assert_fail shlink_validate_utm_value --campaign 'Product Launch'

assert_pass shlink_validate_exact_url 'https://example.com/?utm_source=LinkedIn&utm_medium=organic-social&utm_campaign=Launch'
assert_pass shlink_validate_exact_url 'https://example.com/?utm_source=a&utm_medium=b&utm_campaign=c#section'
assert_fail shlink_validate_exact_url 'https://example.com/#?utm_source=a&utm_medium=b&utm_campaign=c'
assert_fail shlink_validate_exact_url 'https://example.com/?utm_source=&utm_medium=b&utm_campaign=c'
assert_fail shlink_validate_exact_url 'https://example.com/?utm_source=a&utm_source=b&utm_medium=c&utm_campaign=d'
assert_fail shlink_validate_exact_url 'https://example.com/?utm_source=a&utm_medium=b'
assert_pass shlink_validate_exact_mode_flags '' '' '' '' '' '' '' ''
assert_fail shlink_validate_exact_mode_flags '' linkedin '' '' '' '' '' ''
assert_fail shlink_validate_exact_mode_flags '' '' '' '' '' '' launch_2026 ''

built="$(shlink_build_tracked_url 'https://example.com/path?existing=1#details' linkedin organic_social product_launch founder_post paid_search launch_2026 linkedin)"
assert_equal 'https://example.com/path?existing=1&utm_source=linkedin&utm_medium=organic_social&utm_campaign=product_launch&utm_content=founder_post&utm_term=paid_search&utm_id=launch_2026&utm_source_platform=linkedin#details' "$built"
built="$(shlink_build_tracked_url 'https://example.com/#?utm_source=fragment_only' linkedin short_link launch)"
assert_equal 'https://example.com/?utm_source=linkedin&utm_medium=short_link&utm_campaign=launch#?utm_source=fragment_only' "$built"
assert_fail shlink_build_tracked_url 'https://example.com/?utm_source=existing' linkedin short_link launch
assert_fail shlink_build_tracked_url 'https://example.com/' linkedin short-link launch

good_headers=$'HTTP/2 302\r\nlocation: https://example.com/?utm_source=a&utm_medium=b&utm_campaign=c\r\n'
assert_pass shlink_validate_redirect_headers "$good_headers" 'https://example.com/?utm_source=a&utm_medium=b&utm_campaign=c'
assert_fail shlink_validate_redirect_headers "$good_headers" 'https://example.com/wrong'
assert_fail shlink_validate_redirect_headers $'HTTP/2 301\r\nlocation: https://example.com/\r\n' 'https://example.com/'
assert_fail shlink_validate_redirect_headers $'HTTP/2 404\r\n' 'https://example.com/'

stored_target="$(shlink_stored_target '{"longUrl":"https://example.com/target","forwardQuery":false}')"
assert_equal 'https://example.com/target' "$stored_target"
assert_fail shlink_stored_target '{"longUrl":"https://example.com/target","forwardQuery":true}'
assert_fail shlink_stored_target '{"forwardQuery":false}'

assert_pass shlink_status_allowed 200 200 201
assert_fail shlink_status_allowed 500 200 201

temp_dir="$(mktemp -d)"
trap 'rm -rf "$temp_dir"' EXIT
config="$temp_dir/config.json"
printf '%s\n' '{"domains":[{"domain_env":"TEST_SHORT_DOMAIN","protected_slugs":["protected-link"]}]}' >"$config"
export TEST_SHORT_DOMAIN=go.example.com
assert_pass shlink_is_protected_slug "$config" go.example.com protected-link
assert_fail shlink_is_protected_slug "$config" go.example.com ordinary-link
assert_fail shlink_is_protected_slug "$config" other.example.com protected-link

printf 'Passed %d tests.\n' "$PASS_COUNT"
