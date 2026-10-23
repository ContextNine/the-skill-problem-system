#!/usr/bin/env python3
"""Run explicitly authorized local telemetry/repair trials, with isolated state and enforced authority."""
from pathlib import Path
import sys

package = next(parent / "internal/src" for parent in Path(__file__).resolve().parents if (parent / "internal/src/maintenance_live_eval.py").is_file())
sys.path.insert(0, str(package))
from maintenance_live_eval import main

raise SystemExit(main())
