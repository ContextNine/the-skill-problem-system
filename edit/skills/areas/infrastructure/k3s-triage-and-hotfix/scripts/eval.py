#!/usr/bin/env python3
"""Run the offline deterministic replay suite, never production fault injection."""
from pathlib import Path
import sys

package = next(parent / "internal/src" for parent in Path(__file__).resolve().parents if (parent / "internal/src/maintenance_eval.py").is_file())
sys.path.insert(0, str(package))
from maintenance_eval import main

raise SystemExit(main())
