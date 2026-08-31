#!/usr/bin/env python3
"""Portable entrypoint for the shared global agent reconciler."""

from __future__ import annotations

from pathlib import Path
import sys


AGENT_SCRIPTS_DIRECTORY = Path(__file__).resolve().parents[5] / "_package/src"
if str(AGENT_SCRIPTS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(AGENT_SCRIPTS_DIRECTORY))

from global_agent_configuration import main, reconcile_payload as reconcile


if __name__ == "__main__":
    raise SystemExit(main())
