#!/usr/bin/env python3
"""Focused tests for optional Linux watchdog deployment and session tracking."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest import mock


SCRIPT = Path(__file__).with_name("linux_optional_watchdogs.py")
CONTROLLER_SPEC = importlib.util.spec_from_file_location("linux_optional_watchdogs", SCRIPT)
assert CONTROLLER_SPEC and CONTROLLER_SPEC.loader
controller = importlib.util.module_from_spec(CONTROLLER_SPEC)
sys.modules[CONTROLLER_SPEC.name] = controller
CONTROLLER_SPEC.loader.exec_module(controller)

GUARD = (
    Path(__file__).parent.parent
    / "assets/linux-watchdogs/playwright-cli-watchdog.py"
)
GUARD_SPEC = importlib.util.spec_from_file_location("playwright_cli_watchdog", GUARD)
assert GUARD_SPEC and GUARD_SPEC.loader
guard = importlib.util.module_from_spec(GUARD_SPEC)
sys.modules[GUARD_SPEC.name] = guard
GUARD_SPEC.loader.exec_module(guard)


class OptionalLinuxWatchdogTests(unittest.TestCase):
    def test_only_reviewed_linux_worker_is_accepted(self) -> None:
        registry = {
            "machines": [
                {
                    "id": "worker",
                    "enabled": True,
                    "role": "worker",
                    "platform": "linux",
                    "transport": "ssh",
                    "ssh_alias": "worker",
                    "home": "/srv/example-linux/matt",
                }
            ]
        }
        machine = controller.resolve_linux_worker(
            registry, "worker", provision_disabled=False
        )
        self.assertEqual(machine["ssh_alias"], "worker")
        registry["machines"][0]["platform"] = "macos"
        with self.assertRaisesRegex(controller.WatchdogError, "not a Linux worker"):
            controller.resolve_linux_worker(
                registry, "worker", provision_disabled=False
            )

    def test_session_name_and_workspace_hash_match_playwright_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            package = guard.playwright_package_path(home)
            package.parent.mkdir(parents=True)
            package.write_text("{}", encoding="utf-8")
            project = root / "project/subdir"
            project.mkdir(parents=True)
            self.assertEqual(guard.session_name(["-s=review", "open"]), "review")
            self.assertEqual(
                guard.workspace_hash(home, project),
                guard.hashlib.sha1(str(package.resolve()).encode()).hexdigest()[:16],
            )
            (root / "project/.playwright").mkdir()
            self.assertEqual(
                guard.workspace_hash(home, project),
                guard.hashlib.sha1(str((root / "project").resolve()).encode()).hexdigest()[:16],
            )

    def test_dry_run_reports_only_stale_session(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            directory = base / "hash"
            directory.mkdir()
            stale = directory / "stale.session"
            fresh = directory / "fresh.session"
            value = {"name": "session", "version": "1", "socketPath": "/tmp/missing"}
            stale.write_text(json.dumps(value), encoding="utf-8")
            fresh.write_text(json.dumps(value), encoding="utf-8")
            old = time.time() - 7200
            os.utime(stale, (old, old))
            with mock.patch("builtins.print") as output:
                self.assertEqual(
                    guard.sweep(idle_seconds=3600, dry_run=True, base=base), 0
                )
            text = "\n".join(" ".join(map(str, call.args)) for call in output.call_args_list)
            self.assertIn("stale.session", text)
            self.assertNotIn("fresh.session", text)


if __name__ == "__main__":
    unittest.main()
