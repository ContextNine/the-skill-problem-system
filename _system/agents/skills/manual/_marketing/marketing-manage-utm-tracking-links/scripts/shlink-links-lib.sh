#!/usr/bin/env bash

shlink_validation_error() {
    echo "Error: $*" >&2
    return 1
}

shlink_urlencode() {
    jq -rn --arg value "$1" '$value | @uri'
}

shlink_validate_slug() {
    [[ "$1" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] \
        || shlink_validation_error "Slug must use lower-kebab-case"
}

shlink_validate_utm_value() {
    local option="$1"
    local value="$2"
    [[ "$value" =~ ^[a-z0-9]+(_[a-z0-9]+)*$ ]] \
        || shlink_validation_error "$option must use lowercase snake_case"
}

shlink_validate_exact_url() {
    local url="$1"
    local before_fragment query parameter pair name value count
    local -a pairs

    [[ "$url" =~ ^https?:// ]] || shlink_validation_error "Destination must use http:// or https://" || return 1
    before_fragment="${url%%#*}"
    [[ "$before_fragment" == *\?* ]] || shlink_validation_error "Exact URL has no query string" || return 1
    query="${before_fragment#*\?}"
    IFS='&' read -r -a pairs <<<"$query"

    for parameter in utm_source utm_medium utm_campaign; do
        count=0
        value=""
        for pair in "${pairs[@]}"; do
            name="${pair%%=*}"
            if [ "$name" = "$parameter" ]; then
                count=$((count + 1))
                if [[ "$pair" == *=* ]]; then
                    value="${pair#*=}"
                fi
            fi
        done
        [ "$count" -eq 1 ] || shlink_validation_error "Exact URL must contain $parameter exactly once" || return 1
        [ -n "$value" ] || shlink_validation_error "Exact URL has an empty $parameter" || return 1
    done
}

shlink_validate_exact_mode_flags() {
    local value
    for value in "$@"; do
        [ -z "$value" ] || shlink_validation_error "Do not combine --url with target or UTM component flags" || return 1
    done
}

shlink_target_has_utm_query() {
    local before_fragment query pair name
    local -a pairs

    before_fragment="${1%%#*}"
    [[ "$before_fragment" == *\?* ]] || return 1
    query="${before_fragment#*\?}"
    IFS='&' read -r -a pairs <<<"$query"
    for pair in "${pairs[@]}"; do
        name="${pair%%=*}"
        case "$name" in
            utm_source|utm_medium|utm_campaign|utm_content|utm_term|utm_id|utm_source_platform) return 0 ;;
        esac
    done
    return 1
}

shlink_build_tracked_url() {
    local target="$1"
    local source="$2"
    local medium="$3"
    local campaign="$4"
    local content="${5:-}"
    local term="${6:-}"
    local id="${7:-}"
    local source_platform="${8:-}"
    local base fragment separator query

    [[ "$target" =~ ^https?:// ]] || shlink_validation_error "Destination must use http:// or https://" || return 1
    if shlink_target_has_utm_query "$target"; then
        shlink_validation_error "Target already contains UTM parameters; use --url for an exact tracked URL"
        return 1
    fi
    shlink_validate_utm_value --source "$source" || return 1
    shlink_validate_utm_value --medium "$medium" || return 1
    shlink_validate_utm_value --campaign "$campaign" || return 1
    [ -z "$content" ] || shlink_validate_utm_value --content "$content" || return 1
    [ -z "$term" ] || shlink_validate_utm_value --term "$term" || return 1
    [ -z "$id" ] || shlink_validate_utm_value --id "$id" || return 1
    [ -z "$source_platform" ] || shlink_validate_utm_value --source-platform "$source_platform" || return 1

    base="$target"
    fragment=""
    if [[ "$base" == *#* ]]; then
        fragment="#${base#*#}"
        base="${base%%#*}"
    fi
    case "$base" in
        *\?|*\&) separator="" ;;
        *\?*) separator="&" ;;
        *) separator="?" ;;
    esac
    query="utm_source=$(shlink_urlencode "$source")&utm_medium=$(shlink_urlencode "$medium")&utm_campaign=$(shlink_urlencode "$campaign")"
    [ -z "$content" ] || query+="&utm_content=$(shlink_urlencode "$content")"
    [ -z "$term" ] || query+="&utm_term=$(shlink_urlencode "$term")"
    [ -z "$id" ] || query+="&utm_id=$(shlink_urlencode "$id")"
    [ -z "$source_platform" ] || query+="&utm_source_platform=$(shlink_urlencode "$source_platform")"
    printf '%s\n' "${base}${separator}${query}${fragment}"
}

shlink_parse_redirect_headers() {
    local headers="$1"
    SHLINK_REDIRECT_STATUS="$(awk 'toupper($1) ~ /^HTTP\// {code=$2; sub(/\r$/, "", code)} END {print code}' <<<"$headers")"
    SHLINK_REDIRECT_LOCATION="$(awk 'BEGIN{IGNORECASE=1} /^location:/ {sub(/^[^:]+:[[:space:]]*/, ""); sub(/\r$/, ""); value=$0} END {print value}' <<<"$headers")"
}

shlink_validate_redirect_headers() {
    local headers="$1"
    local expected="$2"
    shlink_parse_redirect_headers "$headers"
    [ "$SHLINK_REDIRECT_STATUS" = 302 ] || shlink_validation_error "Expected HTTP 302, got ${SHLINK_REDIRECT_STATUS:-unknown}" || return 1
    [ "$SHLINK_REDIRECT_LOCATION" = "$expected" ] \
        || shlink_validation_error "Redirect target does not match the stored destination" || return 1
}

shlink_stored_target() {
    local body="$1"
    jq -e '.forwardQuery == false and (.longUrl | type == "string" and length > 0)' >/dev/null <<<"$body" \
        || shlink_validation_error "Stored link must have a destination and use forwardQuery=false" \
        || return 1
    jq -r '.longUrl' <<<"$body"
}

shlink_is_protected_slug() {
    local config="$1"
    local domain="$2"
    local slug="$3"
    local domain_env protected_slug configured_domain

    while IFS=$'\t' read -r domain_env protected_slug; do
        [ -n "$domain_env" ] || continue
        configured_domain="${!domain_env:-}"
        [ "$domain" != "$configured_domain" ] || [ "$slug" != "$protected_slug" ] || return 0
    done < <(jq -r '.domains[] | .domain_env as $domain_env | (.protected_slugs // [])[] | [$domain_env, .] | @tsv' "$config")
    return 1
}

shlink_status_allowed() {
    local actual="$1"
    shift
    local expected
    for expected in "$@"; do
        [ "$actual" != "$expected" ] || return 0
    done
    return 1
}
