#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: run-pagespeed-insights.sh URL OUTPUT_DIR [mobile|desktop|both]

Calls PageSpeed Insights API v5 for Performance, Accessibility, Best Practices,
and SEO. PAGESPEED_API_KEY is optional for light use and recommended for automation.
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then usage; exit 0; fi
if [[ $# -lt 2 || $# -gt 3 ]]; then usage >&2; exit 2; fi
command -v curl >/dev/null 2>&1 || { echo "curl is required" >&2; exit 127; }
command -v python3 >/dev/null 2>&1 || { echo "python3 is required for response validation" >&2; exit 127; }

target_url="$1"
output_dir="$2"
device="${3:-both}"
[[ "$target_url" =~ ^https?:// ]] || { echo "URL must begin with http:// or https://" >&2; exit 2; }
[[ "$device" =~ ^(mobile|desktop|both)$ ]] || { echo "Device must be mobile, desktop, or both" >&2; exit 2; }

mkdir -p "$output_dir"
if [[ "$device" == "both" ]]; then devices=(mobile desktop); else devices=("$device"); fi
endpoint="https://pagespeedonline.googleapis.com/pagespeedonline/v5/runPagespeed"

for strategy in "${devices[@]}"; do
  output="$output_dir/pagespeed-${strategy}.json"
  temporary="$(mktemp "${TMPDIR:-/tmp}/pagespeed-response.XXXXXX")"
  trap 'rm -f "$temporary"' EXIT
  curl_args=(
    --silent --show-error --retry 2 --retry-delay 2
    --get "$endpoint"
    --data-urlencode "url=$target_url"
    --data-urlencode "strategy=$strategy"
    --data-urlencode "category=PERFORMANCE"
    --data-urlencode "category=ACCESSIBILITY"
    --data-urlencode "category=BEST_PRACTICES"
    --data-urlencode "category=SEO"
  )
  if [[ -n "${PAGESPEED_API_KEY:-}" ]]; then
    curl_args+=(--data-urlencode "key=$PAGESPEED_API_KEY")
  fi
  echo "Calling PageSpeed Insights: strategy=$strategy"
  http_status="$(curl "${curl_args[@]}" --output "$temporary" --write-out '%{http_code}')"
  if [[ ! "$http_status" =~ ^2 ]]; then
    api_message="$(python3 - "$temporary" <<'PY'
import json
import sys
try:
    payload = json.load(open(sys.argv[1], encoding="utf-8"))
    print(payload.get("error", {}).get("message", "Unknown API error"))
except Exception:
    print("Non-JSON API error")
PY
)"
    echo "PageSpeed Insights HTTP $http_status: $api_message" >&2
    if [[ "$http_status" == "429" && -z "${PAGESPEED_API_KEY:-}" ]]; then
      echo "The shared keyless quota is exhausted; configure PAGESPEED_API_KEY and retry." >&2
    fi
    exit 1
  fi
  python3 -m json.tool "$temporary" >/dev/null
  mv "$temporary" "$output"
  trap - EXIT
  echo "Wrote $output"
done
