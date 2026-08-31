from __future__ import annotations

import importlib.util
from pathlib import Path
import plistlib
import json
import sys
import unittest


SCRIPT = Path(__file__).with_name("sync_agent_notifications.py")
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("sync_agent_notifications", SCRIPT)
assert SPEC and SPEC.loader
sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync)
sync.WORKSPACES = {
    "primary": "Primary machine",
    "linux-worker": "Linux worker",
    "secondary-mac": "Secondary Mac",
}


class SyncAgentNotificationsTests(unittest.TestCase):
    def machines(self):
        return [
            {"id": "primary", "display_name": "Primary machine", "enabled": True, "transport": "local", "home": "/srv/example-macos/matt"},
            {"id": "linux-worker", "display_name": "Linux worker", "enabled": True, "transport": "ssh", "ssh_alias": "linux-worker", "home": "/srv/example-linux/matt"},
            {"id": "secondary-mac", "display_name": "Secondary Mac", "enabled": True, "transport": "ssh", "ssh_alias": "secondary-mac", "home": "/srv/example-macos/mini"},
        ]

    def test_hook_merge_preserves_unrelated_and_is_idempotent(self):
        document = {"theme": "dark", "hooks": {"Stop": [{"hooks": [{"command": "existing", "type": "command"}]}]}}
        command = "/srv/example-linux/matt/.local/bin/workmux-notify enqueue --agent codex --event stop"
        once = sync.merge_stop_hook(document, command)
        twice = sync.merge_stop_hook(once, command)
        self.assertEqual(once, twice)
        self.assertEqual(once["theme"], "dark")
        self.assertEqual(sync.hook_commands(once["hooks"]["Stop"][0]), ["existing"])
        self.assertTrue(sync.has_exact_hook(once, command))

    def test_hook_merge_replaces_old_managed_agent_command(self):
        old = "/old/workmux-notify enqueue --agent codex --event stop"
        new = "/new/workmux-notify enqueue --agent codex --event stop"
        merged = sync.merge_stop_hook({"hooks": {"Stop": [sync.managed_hook(old)]}}, new)
        commands = [value for group in merged["hooks"]["Stop"] for value in sync.hook_commands(group)]
        self.assertEqual(commands, [new])

    def test_codex_managed_stop_hook_is_removed(self):
        command = "/old/workmux-notify enqueue --agent codex --event stop"
        document = {"hooks": {"Stop": [sync.managed_hook(command), {"hooks": [{"command": "keep"}]}]}}
        cleaned = sync.remove_managed_stop_hook(document, "codex")
        commands = [value for group in cleaned["hooks"]["Stop"] for value in sync.hook_commands(group)]
        self.assertEqual(commands, ["keep"])

    def test_codex_notify_merge_preserves_rest_of_toml(self):
        source = 'model = "gpt"\nnotify = ["old", "arg"]\n[projects."/tmp"]\ntrust_level = "trusted"\n'
        command = ["/new/workmux-notify", "codex-notify"]
        merged = sync.merge_notify_command(source, command)
        self.assertEqual(sync.parse_notify_command(merged), command)
        self.assertIn('model = "gpt"', merged)
        self.assertIn('[projects."/tmp"]', merged)

    def test_codex_notify_removal_preserves_rest_of_toml(self):
        source = 'model = "gpt"\nnotify = ["old", "arg"]\n[projects."/tmp"]\ntrust_level = "trusted"\n'
        cleaned = sync.remove_notify_command(source)
        self.assertIsNone(sync.parse_notify_command(cleaned))
        self.assertIn('model = "gpt"', cleaned)
        self.assertIn('[projects."/tmp"]', cleaned)

    def test_managed_notify_restores_saved_passthrough(self):
        managed = ["/srv/example-linux/matt/.local/bin/workmux-notify", "codex-notify"]
        passthrough = ["/Applications/Sky", "turn-ended"]
        self.assertEqual(sync.without_managed_notify(managed, managed, passthrough), passthrough)

    def test_managed_notify_is_removed_from_computer_use_wrapper(self):
        managed = ["/srv/example-macos/matt/.local/bin/workmux-notify", "codex-notify"]
        wrapper = ["/Applications/Sky", "turn-ended", "--previous-notify", json.dumps(managed).replace("/", "\\/")]
        self.assertEqual(sync.without_managed_notify(wrapper, managed, None), ["/Applications/Sky", "turn-ended"])

    def test_primary_config_uses_selected_mesh_sources(self):
        passthrough = ["/Applications/Sky", "turn-ended"]
        config = __import__("json").loads(sync.render_config(self.machines()[0], self.machines(), passthrough))
        self.assertEqual([source["id"] for source in config["sources"]], ["primary", "linux-worker", "secondary-mac"])
        self.assertEqual(config["sources"][1]["ssh_alias"], "linux-worker-mesh")
        self.assertEqual(config["sources"][2]["ssh_alias"], "secondary-mac-mesh")
        self.assertEqual(config["cmux_path"], "/opt/homebrew/bin/cmux")
        self.assertEqual(config["warp"]["terminal_notifier"], "/opt/homebrew/bin/terminal-notifier")
        self.assertEqual(config["warp"]["bundle_id"], "dev.warp.Warp-Stable")
        self.assertEqual(config["codex_notify_passthrough"], passthrough)
        self.assertTrue(config["enabled"])

    def test_disabled_config_retains_only_passthrough_and_no_sources(self):
        passthrough = ["/Applications/Sky", "turn-ended"]
        config = json.loads(sync.render_disabled_config(self.machines()[0], passthrough))
        self.assertFalse(config["enabled"])
        self.assertEqual(config["sources"], [])
        self.assertEqual(config["codex_notify_passthrough"], passthrough)

    def test_remote_config_does_not_poll(self):
        config = __import__("json").loads(sync.render_config(self.machines()[1], self.machines()))
        self.assertEqual(config["sources"], [])

    def test_launch_agent_runs_every_fifteen_seconds(self):
        path, data = sync.launch_agent(self.machines()[0])
        value = plistlib.loads(data)
        self.assertTrue(path.endswith("com.ctx9.workmux-notifications.plist"))
        self.assertEqual(value["StartInterval"], 15)
        self.assertEqual(value["ProgramArguments"][-1], "poll")


if __name__ == "__main__":
    unittest.main()
