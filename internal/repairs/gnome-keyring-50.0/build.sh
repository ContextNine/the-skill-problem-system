#!/bin/bash
set -euo pipefail

# Build the reviewed repair from an authenticated Ubuntu 50.0-1 source package.
# Installation and restarting the live keyring remain explicit operator steps.
repair_dir=$(cd "$(dirname "$0")" && pwd)
source_dir=$(realpath "${1:?Pass a fresh extracted Ubuntu gnome-keyring 50.0-1 source directory}")
grep -q '^gnome-keyring (50.0-1) ' "$source_dir/debian/changelog"
test ! -e "$source_dir/debian/patches/ctx9-missing-client-errors.patch"
patch --dry-run -d "$source_dir" -p1 < "$repair_dir/missing-client-errors.patch"
install -m 644 "$repair_dir/missing-client-errors.patch" "$source_dir/debian/patches/ctx9-missing-client-errors.patch"
printf '%s\n' ctx9-missing-client-errors.patch >> "$source_dir/debian/patches/series"
python3 - "$source_dir/debian/changelog" <<'PY'
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
import sys
path = Path(sys.argv[1])
entry = ('gnome-keyring (50.0-1+ctx9.1) resolute; urgency=high\n\n'
         '  * Return D-Bus errors for missing Secret Service clients instead of aborting.\n'
         '  * Exercise the vanished-client property failure on an isolated D-Bus.\n\n'
         ' -- Context Nine <build@ctx9.com>  ' + format_datetime(datetime.now(timezone.utc)) + '\n\n')
path.write_text(entry + path.read_text())
PY
cd "$source_dir"
dpkg-source --before-build .
dpkg-buildpackage -b -us -uc -j4
