#!/usr/bin/env python3
"""Run the shared AI audit in an existing Fleet checkout."""
from pathlib import Path
import sys

PACKAGE = next(parent / "internal/src" for parent in Path(__file__).resolve().parents if (parent / "internal/src/maintenance_ai.py").is_file())
sys.path.insert(0, str(PACKAGE))
from maintenance_ai import main

if __name__ == "__main__":
    sys.exit(main("triage"))
