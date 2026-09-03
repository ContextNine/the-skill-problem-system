from __future__ import annotations

import importlib.machinery
import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).parent.parent / "assets/terminal-workspaces/workmux-cmux-attach"
LOADER = importlib.machinery.SourceFileLoader("workmux_cmux_attach", str(SCRIPT))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
assert SPEC
attach = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(attach)

attach.PROFILES = ({
    "id": "linux-worker",
    "title": "Linux worker",
    "description": "SSH linux-worker",
    "command": "/srv/example-linux/ctx9/.local/bin/workmux linux-worker",
},)


class WorkmuxCmuxAttachTests(unittest.TestCase):
    def test_screen_classification(self):
        profile = attach.PROFILES[0]
        self.assertTrue(attach.has_tmux_status(profile, "linux-worker 0:btop 1:shell CPU MEM"))
        self.assertTrue(attach.has_shell_prompt("Linux worker ~ > "))
        self.assertTrue(attach.is_disconnected("[cmux] remote session disconnected: linux-worker"))
        self.assertFalse(attach.has_shell_prompt("codex is working"))

    def test_attach_sends_absolute_command_at_idle_prompt(self):
        profile = attach.PROFILES[0]
        screens = iter(["Linux worker ~ > ", "", "linux-worker 0:btop 1:shell CPU MEM"])
        original_cmux = attach.cmux
        original_read = attach.read_screen
        original_sleep = attach.time.sleep
        calls = []
        attach.cmux = lambda *args, **kwargs: calls.append(args)
        attach.read_screen = lambda workspace_ref, surface_ref: next(screens)
        attach.time.sleep = lambda seconds: None
        try:
            self.assertTrue(attach.attach(profile, "workspace:2", "surface:2"))
        finally:
            attach.cmux = original_cmux
            attach.read_screen = original_read
            attach.time.sleep = original_sleep
        sent = [call[-1] for call in calls if call[0] == "send"]
        self.assertEqual(sent, ["   exec /srv/example-linux/ctx9/.local/bin/workmux linux-worker"])

    def test_attach_does_not_touch_unknown_active_screen(self):
        profile = attach.PROFILES[0]
        original_cmux = attach.cmux
        original_read = attach.read_screen
        calls = []
        attach.cmux = lambda *args, **kwargs: calls.append(args)
        attach.read_screen = lambda workspace_ref, surface_ref: "codex is working"
        try:
            self.assertFalse(attach.attach(profile, "workspace:2", "surface:2"))
        finally:
            attach.cmux = original_cmux
            attach.read_screen = original_read
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
