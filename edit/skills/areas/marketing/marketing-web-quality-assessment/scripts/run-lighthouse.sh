#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: run-lighthouse.sh URL OUTPUT_DIR [mobile|desktop|both] [RUNS]

Runs Lighthouse Performance, Accessibility, Best Practices, and SEO audits.
Defaults: device=both, runs=3. Requires Chrome plus Lighthouse or npm/npx.
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then usage; exit 0; fi
if [[ $# -lt 2 || $# -gt 4 ]]; then usage >&2; exit 2; fi

target_url="$1"
output_dir="$2"
device="${3:-both}"
runs="${4:-3}"

[[ "$target_url" =~ ^https?:// ]] || { echo "URL must begin with http:// or https://" >&2; exit 2; }
[[ "$device" =~ ^(mobile|desktop|both)$ ]] || { echo "Device must be mobile, desktop, or both" >&2; exit 2; }
[[ "$runs" =~ ^[1-9][0-9]*$ ]] || { echo "RUNS must be a positive integer" >&2; exit 2; }

if command -v lighthouse >/dev/null 2>&1; then
  runner=(lighthouse)
elif command -v npx >/dev/null 2>&1; then
  runner=(npx --yes lighthouse)
else
  echo "Install current Node.js/npm and Google Chrome, or install Lighthouse globally." >&2
  exit 127
fi

mkdir -p "$output_dir"
if [[ "$device" == "both" ]]; then devices=(mobile desktop); else devices=("$device"); fi

"${runner[@]}" --version | sed 's/^/Lighthouse version: /'
for strategy in "${devices[@]}"; do
  for ((run=1; run<=runs; run++)); do
    report_base="$output_dir/lighthouse-${strategy}-run-${run}"
    args=(
      "$target_url"
      --quiet
      --only-categories=performance,accessibility,best-practices,seo
      --output=json
      --output=html
      --output-path="$report_base"
      --chrome-flags=--headless
    )
    if [[ "$strategy" == "desktop" ]]; then args+=(--preset=desktop); fi
    echo "Running Lighthouse: strategy=$strategy run=$run/$runs"
    "${runner[@]}" "${args[@]}"
  done
done

echo "Reports written under: $output_dir"
