"""Pinned executable installation and integrity failure without daily-machine changes."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import dependency_worker as worker


class BinaryReleaseJourney(unittest.TestCase):
    def test_pinned_install_noop_and_rejected_update_preserve_the_active_binary(self):
        payload = b'#!/bin/sh\nprintf \'{"gitVersion":"v3.1.3"}\\n\'\n'
        recipe = {"manager": "github-binary", "version": "3.1.3", "archives": {"x64": {
            "url": "https://github.com/example/fixture/releases/download/v3.1.3/fixture-linux-amd64",
            "sha256": hashlib.sha256(payload).hexdigest()}}, "binaries_by_arch": {"x64": {"fixture": "fixture"}}}
        dependency = {"id": "fixture", "kind": "package", "platforms": ["linux"], "groups": ["fixture"],
            "required_by": ["fixture"], "lifecycle_doc": "dependencies/fixture.md", "eligibility": "enabled-agent-machines",
            "contract": {"adapter": "package", "install_policy": "required", "update_policy": "declared-recipe",
                         "recipes": {"linux": recipe}, "verify": {"command": "fixture", "args": ["version", "--json"], "exact": "3.1.3"}}}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            environment = {"PATH": str(root / ".local/bin") + os.pathsep + os.defpath}
            request = {"mode": "apply", "manifest": {"schema_version": 2, "dependencies": [dependency]}}
            with (patch.object(worker.Path, "home", return_value=root),
                  patch.object(worker, "platform_name", return_value="linux"),
                  patch.object(worker, "architecture_name", return_value="x64"),
                  patch.object(worker, "environment", return_value=environment),
                  patch.object(worker, "urlopen", side_effect=lambda url, **options: io.BytesIO(payload)) as download):
                preview = worker.reconcile({**request, "mode": "dry-run"})
                self.assertTrue(preview["can_apply"])
                self.assertFalse(preview["ready"])
                self.assertTrue(worker.reconcile(request)["ready"])
                command = root / ".local/bin/fixture"
                active = command.resolve()
                self.assertEqual(active.read_bytes(), payload)
                self.assertEqual(active.stat().st_mode & 0o777, 0o755)
                self.assertTrue(worker.reconcile(request)["ready"])
                self.assertEqual(download.call_count, 1)
                changed = copy.deepcopy(request)
                candidate = changed["manifest"]["dependencies"][0]["contract"]
                candidate["verify"]["exact"] = "3.1.4"
                candidate["recipes"]["linux"]["version"] = "3.1.4"
                archive = candidate["recipes"]["linux"]["archives"]["x64"]
                archive["url"] = archive["url"].replace("v3.1.3", "v3.1.4")
                archive["sha256"] = hashlib.sha256(payload.replace(b"3.1.3", b"3.1.4")).hexdigest()
                with self.assertRaisesRegex(worker.DependencyError, "checksum mismatch"):
                    worker.reconcile(changed)
                self.assertEqual(command.resolve(), active)
                self.assertTrue(worker.reconcile({**request, "mode": "verify"})["ready"])
                active.write_bytes(payload + b"tamper")
                self.assertFalse(worker.reconcile({**request, "mode": "verify"})["ready"])
                with self.assertRaisesRegex(worker.DependencyError, "retained binary checksum mismatch"):
                    worker.reconcile(request)


if __name__ == "__main__":
    unittest.main()
