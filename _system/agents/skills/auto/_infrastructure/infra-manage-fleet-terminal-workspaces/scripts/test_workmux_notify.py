from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).parent.parent / "assets/terminal-workspaces/workmux-notify"
LOADER = importlib.machinery.SourceFileLoader("workmux_notify", str(SCRIPT))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
assert SPEC
notify = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(notify)


class WorkmuxNotifyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.state = self.root / "state"
        self.config = self.root / "config.json"
        self.config.write_text(json.dumps({
            "schema_version": 1,
            "machine": {"id": "test", "name": "Test", "workspace": "Test"},
            "sources": [],
        }))
        self.env = {
            **os.environ,
            "WORKMUX_NOTIFY_STATE_DIR": str(self.state),
            "WORKMUX_NOTIFY_CONFIG": str(self.config),
            "PWD": "/tmp/project-name",
        }

    def tearDown(self):
        self.temporary.cleanup()

    def run_cli(self, *arguments: str, input_text: str = "") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *arguments],
            input=input_text,
            env=self.env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_enqueue_export_ack_round_trip_without_message_text(self):
        payload = json.dumps({"cwd": "/code/impression", "last-assistant-message": "private response"})
        result = self.run_cli("enqueue", "--agent", "codex", "--event", "stop", input_text=payload)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "{}")
        exported = self.run_cli("export")
        event = json.loads(exported.stdout)
        self.assertEqual(event["project"], "impression")
        self.assertEqual(event["agent"], "codex")
        self.assertNotIn("private response", exported.stdout)
        acked = self.run_cli("ack", event["event_id"])
        self.assertEqual(acked.returncode, 0, acked.stderr)
        self.assertEqual(self.run_cli("export").stdout, "")

    def test_codex_notify_argument_queues_completion(self):
        payload = json.dumps({"cwd": "/code/codex-project", "last-assistant-message": "not stored"})
        result = self.run_cli("codex-notify", payload)
        self.assertEqual(result.returncode, 0, result.stderr)
        exported = self.run_cli("export")
        event = json.loads(exported.stdout)
        self.assertEqual(event["agent"], "codex")
        self.assertEqual(event["project"], "codex-project")
        self.assertNotIn("not stored", exported.stdout)

    def test_codex_notify_chains_existing_callback(self):
        marker = self.root / "callback.txt"
        config = json.loads(self.config.read_text())
        config["codex_notify_passthrough"] = [
            sys.executable,
            "-c",
            "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text(sys.argv[2])",
            str(marker),
        ]
        self.config.write_text(json.dumps(config))
        payload = json.dumps({"cwd": "/code/callback-project"})
        result = self.run_cli("codex-notify", payload)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(marker.read_text(), payload)

    def test_disabled_config_does_not_enqueue_but_keeps_passthrough(self):
        marker = self.root / "callback.txt"
        config = json.loads(self.config.read_text())
        config["enabled"] = False
        config["codex_notify_passthrough"] = [
            sys.executable,
            "-c",
            "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text(sys.argv[2])",
            str(marker),
        ]
        self.config.write_text(json.dumps(config))
        payload = json.dumps({"cwd": "/code/disabled-project"})
        result = self.run_cli("codex-notify", payload)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(marker.read_text(), payload)
        self.assertEqual(self.run_cli("export").stdout, "")

    def test_disabled_poll_never_checks_frontends(self):
        config = json.loads(self.config.read_text())
        config["enabled"] = False
        self.config.write_text(json.dumps(config))
        original_config = notify.load_config
        original_context = notify.delivery_context
        notify.load_config = lambda: config
        notify.delivery_context = lambda value: (_ for _ in ()).throw(AssertionError("frontend touched"))
        try:
            self.assertEqual(notify.poll(), 0)
        finally:
            notify.load_config = original_config
            notify.delivery_context = original_context

    def test_invalid_event_moves_to_quarantine(self):
        outbox = self.state / "outbox"
        outbox.mkdir(parents=True)
        (outbox / "bad.json").write_text("not-json")
        self.assertEqual(self.run_cli("export").returncode, 0)
        self.assertTrue((self.state / "quarantine/bad.json").exists())

    def test_target_resolution_requires_exact_main_surface(self):
        tree = {"windows": [{"workspaces": [{
            "ref": "workspace:2",
            "title": "Linux worker",
            "panes": [{"surfaces": [{"ref": "surface:4", "title": "main"}]}],
        }]}]}
        self.assertEqual(notify.target_for(tree, "Linux worker"), ("workspace:2", "surface:4"))
        self.assertIsNone(notify.target_for(tree, "Secondary Mac"))

    def test_notification_contains_metadata_only(self):
        event = {
            "agent": "claude",
            "machine_name": "Secondary Mac",
            "project": "impression",
            "tmux": {"window_index": "3", "window_name": "claude"},
        }
        self.assertEqual(
            notify.render_notification(event),
            ("Claude · Secondary Mac", "Completed in impression", "tmux 3:claude"),
        )

    def test_warp_notification_activates_warp_and_groups_event(self):
        config = {
            "warp": {
                "terminal_notifier": "/opt/homebrew/bin/terminal-notifier",
                "bundle_id": "dev.warp.Warp-Stable",
                "icon": "/Applications/Warp.app/Contents/Resources/AppIcon.icns",
            }
        }
        event = {
            "event_id": "a" * 32,
            "agent": "codex",
            "machine_name": "Linux worker",
            "project": "impression",
            "tmux": {"window_index": "2", "window_name": "codex"},
        }
        command = notify.warp_notification_command(config, event)
        self.assertEqual(command[0], "/opt/homebrew/bin/terminal-notifier")
        self.assertEqual(command[command.index("-activate") + 1], "dev.warp.Warp-Stable")
        self.assertEqual(command[command.index("-group") + 1], event["event_id"])
        self.assertIn("tmux 2:codex", command)

    def test_delivery_context_prefers_warp_without_touching_cmux(self):
        original_warp = notify.warp_running
        original_tree = notify.cmux_tree
        notify.warp_running = lambda config: True
        notify.cmux_tree = lambda config: (_ for _ in ()).throw(AssertionError("cmux touched"))
        try:
            self.assertEqual(notify.delivery_context({}), {"kind": "warp"})
        finally:
            notify.warp_running = original_warp
            notify.cmux_tree = original_tree

    def test_delivery_context_falls_back_to_cmux(self):
        tree = {"windows": []}
        original_warp = notify.warp_running
        original_tree = notify.cmux_tree
        notify.warp_running = lambda config: False
        notify.cmux_tree = lambda config: tree
        try:
            self.assertEqual(notify.delivery_context({}), {"kind": "cmux", "tree": tree})
        finally:
            notify.warp_running = original_warp
            notify.cmux_tree = original_tree

    def test_poll_keeps_queues_when_no_frontend_is_available(self):
        original_config = notify.load_config
        original_context = notify.delivery_context
        original_sources = notify.source_events
        notify.load_config = lambda: {"sources": [{"id": "test"}]}
        notify.delivery_context = lambda config: None
        notify.source_events = lambda source: (_ for _ in ()).throw(AssertionError("source queue touched"))
        try:
            self.assertEqual(notify.poll(), 0)
        finally:
            notify.load_config = original_config
            notify.delivery_context = original_context
            notify.source_events = original_sources

    def test_successful_warp_delivery_is_acknowledged_once(self):
        event = {
            "event_id": "b" * 32,
            "created_at": "2026-07-22T00:00:00Z",
            "machine_id": "test",
            "machine_name": "Test",
            "agent": "codex",
            "event": "stop",
            "project": "project",
            "tmux": {},
            "schema_version": 1,
        }
        source = {"id": "test", "workspace": "Test", "transport": "local"}
        originals = {
            name: getattr(notify, name)
            for name in (
                "load_config",
                "delivery_context",
                "load_delivered",
                "source_events",
                "deliver_event",
                "save_delivered",
                "source_ack",
            )
        }
        acknowledgments = []
        notify.load_config = lambda: {"sources": [source]}
        notify.delivery_context = lambda config: {"kind": "warp"}
        notify.load_delivered = lambda: {}
        notify.source_events = lambda value: [event]
        notify.deliver_event = lambda config, context, value, item: True
        notify.save_delivered = lambda value: None
        notify.source_ack = lambda value, event_ids: acknowledgments.extend(event_ids)
        try:
            self.assertEqual(notify.poll(), 0)
            self.assertEqual(acknowledgments, [event["event_id"]])
        finally:
            for name, value in originals.items():
                setattr(notify, name, value)


if __name__ == "__main__":
    unittest.main()
