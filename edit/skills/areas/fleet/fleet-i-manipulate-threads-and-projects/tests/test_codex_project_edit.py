"""Saved-project migration preserves chat identity and unrelated desktop state."""
import importlib.util
import json
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("project_edit", Path(__file__).parents[1] / "scripts/codex_project_edit.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ProjectEditIntegrationTest(unittest.TestCase):
    def test_apply_backup_preservation_and_repeat(self):
        state = {"remote-projects": [{"id": "p", "hostId": "remote-ssh-codex-managed:worker", "remotePath": "/home/user/Code/old", "label": "old"}],
                 "thread-project-assignments": {"t": {"projectKind": "remote", "projectId": "retired-project", "hostId": "remote-ssh-discovered:worker-mesh"}},
                 "pinned-thread-ids": ["t"], "project-order": ["p"], "sidebar-project-thread-orders": {"p": ["t"]},
                 "unrelated": {"retain": True}}
        operations = [{"project_id": "p", "host_id": "remote-ssh-codex-managed:worker", "from_path": "/home/user/Code/old",
                       "to_path": "/home/user/Code/group/new", "name": "new", "thread_ids": ["t", "implicit"], "previous_assignments": {"t": state["thread-project-assignments"]["t"]}}]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / ".codex-global-state.json"
            path.write_text(json.dumps(state))
            original = path.read_bytes()
            with patch.object(module, "desktop_is_running", return_value=False):
                report = module.apply_file(path, operations)
                repeated = module.apply_file(path, operations)
            updated = json.loads(path.read_text())
            self.assertEqual((Path(report["backup"]) / path.name).read_bytes(), original)
            self.assertEqual(updated["remote-projects"][0]["id"], "p")
            self.assertEqual(updated["remote-projects"][0]["remotePath"], operations[0]["to_path"])
            self.assertEqual(set(updated["thread-project-assignments"]), {"t", "implicit"})
            for key in ["pinned-thread-ids", "project-order", "sidebar-project-thread-orders", "unrelated"]:
                self.assertEqual(updated[key], state[key])
            self.assertEqual(repeated["mode"], "unchanged")

    def test_detect_full_macos_executable_path(self):
        processes = "/usr/bin/ssh\n/Applications/ChatGPT.app/Contents/MacOS/ChatGPT\n"
        with patch.object(module.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, stdout=processes)):
            self.assertTrue(module.desktop_is_running())

    def test_running_writer_refuses_before_backup_or_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "state.json"
            path.write_text('{}')
            with patch.object(module, "desktop_is_running", return_value=True):
                with self.assertRaisesRegex(SystemExit, "desktop is running"):
                    module.apply_file(path, [])
            self.assertEqual(path.read_text(), '{}')
            self.assertFalse((path.parent / "thread-port-backups").exists())


if __name__ == "__main__":
    unittest.main()
