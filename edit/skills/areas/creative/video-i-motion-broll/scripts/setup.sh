#!/usr/bin/env bash
# Install or verify the project's NumPy, Playwright, and Chromium runtime.
set -euo pipefail
VERIFY=false
if [ "${1:-}" = "--verify" ]; then VERIFY=true; shift; fi
MOTION_DIR="${1:-./motion}"
missing=()
for command in node npm python3 ffmpeg ffprobe; do
  command -v "$command" >/dev/null || missing+=("$command")
done
if [ ${#missing[@]} -gt 0 ]; then echo "Missing: ${missing[*]}"; exit 1; fi
node -e 'if (Number(process.versions.node.split(".")[0]) < 18) process.exit(1)'
encoders="$(ffmpeg -hide_banner -encoders 2>/dev/null)"
if ! grep -q prores_ks <<< "$encoders"; then
  echo "ffmpeg needs the prores_ks encoder for transparent panels."; exit 1
fi
if [ "$VERIFY" = false ]; then
  mkdir -p "$MOTION_DIR"/{clips,dist,out,work,inputs}
  [ -x "$MOTION_DIR/.venv/bin/python" ] || python3 -m venv "$MOTION_DIR/.venv"
  "$MOTION_DIR/.venv/bin/python" -c 'import numpy' 2>/dev/null || \
    "$MOTION_DIR/.venv/bin/python" -m pip install numpy
  (
    cd "$MOTION_DIR"
    [ -f package.json ] || printf '%s\n' '{"private":true}' > package.json
    [ -d node_modules/playwright ] || npm install --silent playwright
    npx --no-install playwright install chromium
  )
fi
"$MOTION_DIR/.venv/bin/python" -c 'import numpy; print("NumPy", numpy.__version__)'
(
  cd "$MOTION_DIR"
  node -e 'const fs=require("fs"); const {chromium}=require("playwright"); if (!fs.existsSync(chromium.executablePath())) throw new Error("Chromium is missing"); console.log("Playwright and Chromium ready");'
)
echo "Ready. Clips go in $MOTION_DIR/clips, renders in $MOTION_DIR/out."
