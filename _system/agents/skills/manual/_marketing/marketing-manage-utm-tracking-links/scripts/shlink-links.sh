#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=shlink-links-lib.sh
source "$SCRIPT_DIR/shlink-links-lib.sh"

usage() {
    cat <<'EOF'
Usage:
  shlink-links.sh create --domain DOMAIN --slug SLUG (--url URL | --target URL --source VALUE --medium VALUE --campaign VALUE) [--content VALUE] [--term VALUE] [--id VALUE] [--source-platform VALUE]
  shlink-links.sh update --domain DOMAIN --slug SLUG (--url URL | --target URL --source VALUE --medium VALUE --campaign VALUE) [--content VALUE] [--term VALUE] [--id VALUE] [--source-platform VALUE] [--allow-permanent]
  shlink-links.sh delete --domain DOMAIN --slug SLUG --yes [--allow-permanent]
  shlink-links.sh get --domain DOMAIN --slug SLUG
  shlink-links.sh list --domain DOMAIN [--search VALUE] [--limit 1-500]
  shlink-links.sh check --domain DOMAIN --slug SLUG
  shlink-links.sh visits --domain DOMAIN --slug SLUG [--limit 1-500]
  shlink-links.sh domains [--config PATH]

All commands accept --config PATH. Run `domains` to list configured domains.
EOF
}

fail() {
    echo "Error: $*" >&2
    exit 1
}

[ "$#" -gt 0 ] || { usage; exit 1; }
COMMAND="$1"
shift

case "$COMMAND" in
    create|update|delete|get|list|check|visits|domains) ;;
    help|-h|--help) usage; exit 0 ;;
    *) fail "Unknown command: $COMMAND" ;;
esac

DOMAIN=""
SLUG=""
EXACT_URL=""
TARGET=""
UTM_SOURCE=""
UTM_MEDIUM=""
UTM_CAMPAIGN=""
UTM_CONTENT=""
UTM_TERM=""
UTM_ID=""
UTM_SOURCE_PLATFORM=""
SEARCH=""
LIMIT=100
CONFIRMED=false
ALLOW_PERMANENT=false
CONFIG_PATH="${UTM_LINKS_CONFIG:-}"

while [ "$#" -gt 0 ]; do
    case "$1" in
        --domain) [ "$#" -ge 2 ] || fail "--domain needs a value"; DOMAIN="$2"; shift 2 ;;
        --slug) [ "$#" -ge 2 ] || fail "--slug needs a value"; SLUG="$2"; shift 2 ;;
        --url) [ "$#" -ge 2 ] || fail "--url needs a value"; EXACT_URL="$2"; shift 2 ;;
        --target) [ "$#" -ge 2 ] || fail "--target needs a value"; TARGET="$2"; shift 2 ;;
        --source) [ "$#" -ge 2 ] || fail "--source needs a value"; UTM_SOURCE="$2"; shift 2 ;;
        --medium) [ "$#" -ge 2 ] || fail "--medium needs a value"; UTM_MEDIUM="$2"; shift 2 ;;
        --campaign) [ "$#" -ge 2 ] || fail "--campaign needs a value"; UTM_CAMPAIGN="$2"; shift 2 ;;
        --content) [ "$#" -ge 2 ] || fail "--content needs a value"; UTM_CONTENT="$2"; shift 2 ;;
        --term) [ "$#" -ge 2 ] || fail "--term needs a value"; UTM_TERM="$2"; shift 2 ;;
        --id) [ "$#" -ge 2 ] || fail "--id needs a value"; UTM_ID="$2"; shift 2 ;;
        --source-platform) [ "$#" -ge 2 ] || fail "--source-platform needs a value"; UTM_SOURCE_PLATFORM="$2"; shift 2 ;;
        --search) [ "$#" -ge 2 ] || fail "--search needs a value"; SEARCH="$2"; shift 2 ;;
        --limit) [ "$#" -ge 2 ] || fail "--limit needs a value"; LIMIT="$2"; shift 2 ;;
        --yes) CONFIRMED=true; shift ;;
        --allow-permanent) ALLOW_PERMANENT=true; shift ;;
        --config) [ "$#" -ge 2 ] || fail "--config needs a value"; CONFIG_PATH="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) fail "Unknown option: $1" ;;
    esac
done

for tool in curl jq; do
    command -v "$tool" >/dev/null 2>&1 || fail "Missing required command: $tool"
done

VAULT_ROOT="${VAULT_ROOT:-$(vault root 2>/dev/null || true)}"
[ -n "$VAULT_ROOT" ] || fail "Cannot resolve vault root; set VAULT_ROOT"
CONFIG_PATH="${CONFIG_PATH:-$VAULT_ROOT/_system/agents/_package/instance/skills/config/marketing-manage-utm-tracking-links/private/config.json}"
[ -f "$CONFIG_PATH" ] || fail "Tracking-link config not found: $CONFIG_PATH"
jq -e '
    .schema_version == 1
    and .provider == "shlink"
    and (.domains | type == "array" and length > 0)
    and all(.domains[];
        (.domain_env | type == "string" and length > 0)
        and ((.protected_slugs // []) | type == "array")
    )
' "$CONFIG_PATH" >/dev/null \
    || fail "Invalid Shlink tracking-link config: $CONFIG_PATH"
while IFS= read -r protected_slug; do
    shlink_validate_slug "$protected_slug" || fail "Invalid protected slug in config: $protected_slug"
done < <(jq -r '.domains[] | (.protected_slugs // [])[]' "$CONFIG_PATH")

REPOSITORY_ID="$(jq -r '.repository_id' "$CONFIG_PATH")"
REPOSITORY_REGISTRY="$VAULT_ROOT/_system/agents/_package/instance/fleet/workspaces.json"
[ -f "$REPOSITORY_REGISTRY" ] || fail "Repository registry not found: $REPOSITORY_REGISTRY"
REPOSITORY_PATH="$(jq -r --arg id "$REPOSITORY_ID" '.repositories[$id].path // empty' "$REPOSITORY_REGISTRY")"
[ -n "$REPOSITORY_PATH" ] || fail "Repository ID not found in topology config: $REPOSITORY_ID"
REPOSITORY_PATH="${REPOSITORY_PATH/#\~/$HOME}"
SHLINK_REPOSITORY_DIR="${SHLINK_REPOSITORY_DIR:-$REPOSITORY_PATH}"
ENV_LOADER="$(jq -r '.env_loader' "$CONFIG_PATH")"
[ -f "$SHLINK_REPOSITORY_DIR/$ENV_LOADER" ] || fail "Configured env loader not found: $SHLINK_REPOSITORY_DIR/$ENV_LOADER"
export ENV_SYNCED=true
# shellcheck source=/dev/null
source "$SHLINK_REPOSITORY_DIR/$ENV_LOADER" >/dev/null

NAMESPACE_ENV="$(jq -r '.namespace_env' "$CONFIG_PATH")"
API_KEY_ENV="$(jq -r '.api_key_env' "$CONFIG_PATH")"
MANAGEMENT_HOST_ENV="$(jq -r '.management_host_env' "$CONFIG_PATH")"
DOMAIN_ENVS=()
while IFS= read -r domain_env; do DOMAIN_ENVS+=("$domain_env"); done < <(jq -r '.domains[].domain_env' "$CONFIG_PATH")
required_env=("$NAMESPACE_ENV" "$API_KEY_ENV" "$MANAGEMENT_HOST_ENV" "${DOMAIN_ENVS[@]}")
for var in "${required_env[@]}"; do
    [ -n "${!var:-}" ] || fail "Missing required environment variable: $var"
done

SHLINK_NAMESPACE_VALUE="${!NAMESPACE_ENV}"
SHLINK_API_KEY_VALUE="${!API_KEY_ENV}"
SHLINK_MANAGEMENT_HOST="${!MANAGEMENT_HOST_ENV}"
API_BASE_TEMPLATE="$(jq -r '.api_base' "$CONFIG_PATH")"
SHLINK_API_BASE="${SHLINK_API_BASE:-${API_BASE_TEMPLATE//\{namespace\}/$SHLINK_NAMESPACE_VALUE}}"

if [ "$COMMAND" = domains ]; then
    for var in "${DOMAIN_ENVS[@]}"; do printf '%s\n' "${!var}"; done
    exit 0
fi

[ -n "$DOMAIN" ] || fail "--domain is required"
DOMAIN_ALLOWED=false
for var in "${DOMAIN_ENVS[@]}"; do [ "$DOMAIN" != "${!var}" ] || DOMAIN_ALLOWED=true; done
[ "$DOMAIN_ALLOWED" = true ] || fail "Unsupported short domain: $DOMAIN"

if [ "$COMMAND" != list ]; then
    [ -n "$SLUG" ] || fail "--slug is required"
    shlink_validate_slug "$SLUG" || exit 1
fi

[[ "$LIMIT" =~ ^[0-9]+$ ]] && [ "$LIMIT" -ge 1 ] && [ "$LIMIT" -le 500 ] \
    || fail "--limit must be between 1 and 500"

api_request() {
    local method="$1"
    local path="$2"
    local payload="${3:-}"
    local response
    if [ -n "$payload" ]; then
        response="$(curl -sS --max-time 30 -X "$method" \
            -H "X-Api-Key: $SHLINK_API_KEY_VALUE" \
            -H "Host: $SHLINK_MANAGEMENT_HOST" \
            -H "Content-Type: application/json" \
            --data "$payload" -w $'\n%{http_code}' "$SHLINK_API_BASE$path")"
    else
        response="$(curl -sS --max-time 30 -X "$method" \
            -H "X-Api-Key: $SHLINK_API_KEY_VALUE" \
            -H "Host: $SHLINK_MANAGEMENT_HOST" \
            -w $'\n%{http_code}' "$SHLINK_API_BASE$path")"
    fi
    API_STATUS="${response##*$'\n'}"
    API_BODY="${response%$'\n'*}"
}

api_failure() {
    echo "Error: Shlink API returned HTTP $API_STATUS." >&2
    jq -c '{type, title, detail, status}' <<<"$API_BODY" >&2 2>/dev/null || true
    exit 1
}

domain_query() {
    printf 'domain=%s' "$(shlink_urlencode "$DOMAIN")"
}

get_current() {
    api_request GET "/short-urls/$SLUG?$(domain_query)"
}

print_link() {
    jq '{shortUrl, longUrl, domain, shortCode, forwardQuery, dateCreated, title, tags, visitsSummary}' <<<"$API_BODY"
}

build_tracked_url() {
    [ -n "$TARGET" ] || fail "Use --url or --target"
    [ -z "$EXACT_URL" ] || fail "Do not combine --url and --target"
    [ -n "$UTM_SOURCE" ] || fail "--source is required with --target"
    [ -n "$UTM_MEDIUM" ] || fail "--medium is required with --target"
    [ -n "$UTM_CAMPAIGN" ] || fail "--campaign is required with --target"
    TRACKED_URL="$(shlink_build_tracked_url "$TARGET" "$UTM_SOURCE" "$UTM_MEDIUM" "$UTM_CAMPAIGN" \
        "$UTM_CONTENT" "$UTM_TERM" "$UTM_ID" "$UTM_SOURCE_PLATFORM")" || exit 1
}

prepare_tracked_url() {
    if [ -n "$EXACT_URL" ]; then
        shlink_validate_exact_mode_flags "$TARGET" "$UTM_SOURCE" "$UTM_MEDIUM" "$UTM_CAMPAIGN" \
            "$UTM_CONTENT" "$UTM_TERM" "$UTM_ID" "$UTM_SOURCE_PLATFORM" || exit 1
        TRACKED_URL="$EXACT_URL"
        shlink_validate_exact_url "$TRACKED_URL" || exit 1
    else
        build_tracked_url
    fi
}

case "$COMMAND" in
    create)
        prepare_tracked_url
        get_current
        if [ "$API_STATUS" = 200 ]; then
            if jq -e --arg url "$TRACKED_URL" '.longUrl == $url and .forwardQuery == false' >/dev/null <<<"$API_BODY"; then
                echo "Unchanged: https://$DOMAIN/$SLUG"
                print_link
                exit 0
            fi
            fail "https://$DOMAIN/$SLUG already exists with conflicting configuration"
        fi
        [ "$API_STATUS" = 404 ] || api_failure
        payload="$(jq -cn --arg longUrl "$TRACKED_URL" --arg customSlug "$SLUG" --arg domain "$DOMAIN" \
            '{longUrl:$longUrl, customSlug:$customSlug, domain:$domain, forwardQuery:false, findIfExists:false}')"
        api_request POST /short-urls "$payload"
        shlink_status_allowed "$API_STATUS" 200 201 || api_failure
        get_current
        shlink_status_allowed "$API_STATUS" 200 || api_failure
        jq -e --arg url "$TRACKED_URL" '.longUrl == $url and .forwardQuery == false' >/dev/null <<<"$API_BODY" \
            || fail "Created link failed verification"
        echo "Created: https://$DOMAIN/$SLUG"
        print_link
        ;;
    update)
        prepare_tracked_url
        if shlink_is_protected_slug "$CONFIG_PATH" "$DOMAIN" "$SLUG" && [ "$ALLOW_PERMANENT" != true ]; then
            fail "Protected-link update requires --allow-permanent and explicit user approval"
        fi
        get_current
        [ "$API_STATUS" = 200 ] || { [ "$API_STATUS" = 404 ] && fail "Link not found: https://$DOMAIN/$SLUG"; api_failure; }
        if jq -e --arg url "$TRACKED_URL" '.longUrl == $url and .forwardQuery == false' >/dev/null <<<"$API_BODY"; then
            echo "Unchanged: https://$DOMAIN/$SLUG"
            print_link
            exit 0
        fi
        payload="$(jq -cn --arg longUrl "$TRACKED_URL" '{longUrl:$longUrl, forwardQuery:false}')"
        api_request PATCH "/short-urls/$SLUG?$(domain_query)" "$payload"
        [ "$API_STATUS" = 200 ] || api_failure
        get_current
        [ "$API_STATUS" = 200 ] || api_failure
        jq -e --arg url "$TRACKED_URL" '.longUrl == $url and .forwardQuery == false' >/dev/null <<<"$API_BODY" \
            || fail "Updated link failed verification"
        echo "Updated: https://$DOMAIN/$SLUG"
        print_link
        ;;
    delete)
        [ "$CONFIRMED" = true ] || fail "Deletion requires --yes after explicit user request"
        if shlink_is_protected_slug "$CONFIG_PATH" "$DOMAIN" "$SLUG" && [ "$ALLOW_PERMANENT" != true ]; then
            fail "Protected-link deletion requires --allow-permanent and explicit user approval"
        fi
        get_current
        if [ "$API_STATUS" = 404 ]; then
            echo "Already absent: https://$DOMAIN/$SLUG"
            exit 0
        fi
        [ "$API_STATUS" = 200 ] || api_failure
        api_request DELETE "/short-urls/$SLUG?$(domain_query)"
        shlink_status_allowed "$API_STATUS" 204 || api_failure
        get_current
        [ "$API_STATUS" = 404 ] || fail "Deleted link still resolves through API"
        echo "Deleted: https://$DOMAIN/$SLUG"
        ;;
    get)
        get_current
        [ "$API_STATUS" = 200 ] || { [ "$API_STATUS" = 404 ] && fail "Link not found: https://$DOMAIN/$SLUG"; api_failure; }
        print_link
        ;;
    list)
        path="/short-urls?itemsPerPage=$LIMIT&$(domain_query)"
        [ -z "$SEARCH" ] || path+="&searchTerm=$(shlink_urlencode "$SEARCH")"
        api_request GET "$path"
        [ "$API_STATUS" = 200 ] || api_failure
        jq '.shortUrls | {data: [.data[] | {shortUrl, longUrl, domain, shortCode, forwardQuery, dateCreated, title, tags, visitsSummary}], pagination}' <<<"$API_BODY"
        ;;
    check)
        get_current
        [ "$API_STATUS" = 200 ] || { [ "$API_STATUS" = 404 ] && fail "Link not found: https://$DOMAIN/$SLUG"; api_failure; }
        expected_location="$(shlink_stored_target "$API_BODY")" || exit 1
        if ! headers="$(curl -sS --max-time 30 -D - -o /dev/null "https://$DOMAIN/$SLUG?attempted_override=true")"; then
            fail "Could not request public short URL"
        fi
        shlink_parse_redirect_headers "$headers"
        printf 'HTTP %s\nLocation: %s\n' "$SHLINK_REDIRECT_STATUS" "$SHLINK_REDIRECT_LOCATION"
        shlink_validate_redirect_headers "$headers" "$expected_location" || exit 1
        ;;
    visits)
        api_request GET "/short-urls/$SLUG/visits?$(domain_query)&itemsPerPage=$LIMIT"
        [ "$API_STATUS" = 200 ] || api_failure
        jq '.visits | {data: [.data[] | {date, referer, userAgent, potentialBot, visitLocation, visitedUrl, redirectUrl}], pagination}' <<<"$API_BODY"
        ;;
esac
