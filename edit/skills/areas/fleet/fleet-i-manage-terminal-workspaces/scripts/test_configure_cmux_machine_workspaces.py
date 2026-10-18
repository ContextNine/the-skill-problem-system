from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("configure_cmux_machine_workspaces.py")
SPEC = importlib.util.spec_from_file_location("configure_cmux_machine_workspaces", SCRIPT)
assert SPEC and SPEC.loader
layout = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(layout)

layout.WORKSPACES = [
    {"id": "primary", "title": "Primary machine", "color": "#AD1457", "description": "Local primary", "transport": "local", "keep_titles": ("Home", "main")},
    {"id": "linux-worker", "title": "Linux worker", "color": "#1565C0", "description": "SSH linux-worker", "transport": "ssh", "keep_titles": ("Work", "main"), "ssh_alias": "linux-worker", "remote_workmux": "/srv/example-linux/ctx9/.local/bin/workmux"},
    {"id": "secondary-mac", "title": "Secondary Mac", "color": "#2E7D32", "description": "SSH secondary-mac", "transport": "ssh", "keep_titles": ("Work", "main"), "ssh_alias": "secondary-mac", "remote_workmux": "/srv/example-macos/neomk2/.local/bin/workmux", "remote_path": "/srv/example-macos/neomk2/.local/bin:/usr/local/bin:/usr/bin:/bin"},
    {"id": "worker-mac", "title": "Worker Mac", "color": "#6A1B9A", "description": "SSH worker-mac", "transport": "ssh", "keep_titles": ("Work", "main"), "ssh_alias": "worker-mac", "remote_workmux": "/srv/example-macos/ctx9/.local/bin/workmux", "remote_path": "/srv/example-macos/ctx9/.local/bin:/opt/homebrew/bin:/usr/bin:/bin"},
]


def workspace(ref, title, surface_titles, pinned=True, description=None):
    return {
        "ref": ref,
        "title": title,
        "pinned": pinned,
        "description": description,
        "panes": [{"surfaces": [{"ref": f"{ref}-{index}", "title": name, "type": "terminal"} for index, name in enumerate(surface_titles)]}],
    }


class ConfigureCmuxTests(unittest.TestCase):
    def tree(self):
        return {"windows": [{"workspaces": [
            workspace("workspace:1", "Machines", ["Terminal"], False),
            workspace("workspace:2", "Primary machine", ["Home", "Code"]),
            workspace("workspace:3", "Linux worker", ["Monitor", "Work"]),
            workspace("workspace:4", "Secondary Mac", ["Work"]),
            workspace("workspace:5", "Worker Mac", ["Work"]),
        ]}]}

    def test_plans_retained_surfaces_and_cleanup(self):
        actions = layout.plan_layout(self.tree())
        retained = [(action["profile"]["id"], action["surface"]) for action in actions if action["action"] == "retain-surface"]
        self.assertEqual(
            retained,
            [
                ("primary", "workspace:2-0"),
                ("linux-worker", "workspace:3-1"),
                ("secondary-mac", "workspace:4-0"),
                ("worker-mac", "workspace:5-0"),
            ],
        )
        self.assertEqual(len([action for action in actions if action["action"] == "close-surface"]), 2)
        self.assertEqual(len([action for action in actions if action["action"] == "close-workspace"]), 1)

    def test_missing_workspace_is_created(self):
        tree = self.tree()
        tree["windows"][0]["workspaces"].pop()
        actions = layout.plan_layout(tree)
        self.assertEqual(
            [
                action["profile"]["id"]
                for action in actions
                if action["action"] == "create-workspace"
            ],
            ["worker-mac"],
        )

    def test_stale_managed_migration_is_resumable(self):
        tree = self.tree()
        tree["windows"][0]["workspaces"].append(workspace("workspace:9", "Linux worker workmux migration", ["main"]))
        actions = layout.plan_layout(tree)
        self.assertEqual([action["workspace"] for action in actions if action["action"] == "resume-migration"], ["workspace:9"])
        self.assertFalse(any(action["action"] == "unexpected-workspace" and action["workspace"] == "workspace:9" for action in actions))

    def test_sidebar_marker_is_idempotent(self):
        source = '{\n  "schemaVersion": 1,\n  "app": {}\n}\n'
        once = layout.update_cmux_json(source, Path("/srv/example-macos/tester"))
        twice = layout.update_cmux_json(once, Path("/srv/example-macos/tester"))
        self.assertEqual(once, twice)
        self.assertIn('"showPorts": false', once)
        self.assertIn('"hideAllDetails": true', once)
        self.assertIn('"showBranchDirectory": false', once)
        self.assertIn('"Reconnect machine tmux"', once)
        self.assertIn('"Open Warp Machine Workspaces"', once)
        self.assertIn("managed machine launch configuration", once)
        self.assertIn('/srv/example-macos/tester/.local/bin/workmux-cmux-attach', once)

    def test_saved_commands_refuse_unmanaged_commands_array(self):
        source = '{\n  "schemaVersion": 1,\n  "commands": []\n}\n'
        with self.assertRaisesRegex(ValueError, "unmanaged top-level"):
            layout.update_cmux_json(source)

    def test_saved_commands_run_in_self_closing_local_workspaces(self):
        block = layout.saved_commands_block(Path("/srv/example-macos/tester"))
        self.assertIn('"workspace": {', block)
        self.assertIn('CMUX_WORKSPACE_ID', block)
        self.assertIn('/opt/homebrew/bin/cmux close-workspace', block)
        self.assertIn("warp://launch/Machine%20Workspaces", block)

    def test_atomic_update_backs_up_changed_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cmux.json"
            path.write_text("old")
            backup = layout.atomic_update(path, "new", "STAMP")
            self.assertEqual(path.read_text(), "new")
            self.assertEqual(backup.read_text(), "old")

    def test_atomic_update_repairs_mode_when_content_matches(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "helper"
            path.write_text("same")
            path.chmod(0o644)
            layout.atomic_update(path, "same", "STAMP", 0o755)
            self.assertEqual(path.stat().st_mode & 0o777, 0o755)

    def test_verify_rejects_wrong_order_and_extra_surface(self):
        original_windows = layout.session_windows
        original_process = layout.session_btop_process
        original_screen = layout.read_surface_screen
        layout.session_windows = lambda profile: ["0:btop", "1:shell"]
        layout.session_btop_process = lambda profile: "btop"
        layout.read_surface_screen = lambda workspace_ref, surface_ref: "primary secondary-mac linux-worker 0:btop 1:shell CPU MEM"
        try:
            tree = self.tree()
            errors = layout.verify_layout(tree)
        finally:
            layout.session_windows = original_windows
            layout.session_btop_process = original_process
            layout.read_surface_screen = original_screen
        self.assertIn("workspace order/titles differ", errors)
        self.assertTrue(any("expected one main surface" in error for error in errors))

    def test_default_mode_is_dry_run(self):
        args = layout.parser().parse_args([])
        self.assertFalse(args.apply)
        self.assertFalse(args.verify)

    def test_target_selects_only_exact_enabled_profile(self):
        selected = layout.select_profiles(["worker-mac"])
        self.assertEqual([profile["id"] for profile in selected], ["worker-mac"])
        with self.assertRaisesRegex(ValueError, "unknown enabled"):
            layout.select_profiles(["Worker Mac"])

    def test_surface_status_detection(self):
        profile = layout.WORKSPACES[1]
        status = "linux-worker  0:btop  1:shell  CPU 1% · MEM 17%"
        self.assertTrue(layout.screen_has_tmux_status(profile, status))
        self.assertFalse(layout.screen_has_tmux_status(profile, status.replace("CPU", "LOAD")))

    def test_attachment_retries_with_drop_safe_leading_spaces(self):
        profile = layout.WORKSPACES[1]
        status = "linux-worker  0:btop  1:shell  CPU 1% · MEM 17%"
        screens = iter([""] + [""] * 30 + [status])
        original_cmux = layout.cmux
        original_read = layout.read_surface_screen
        original_wait = layout.wait_for_shell
        original_sleep = layout.time.sleep
        calls = []
        layout.cmux = lambda *args, **kwargs: calls.append(args)
        layout.read_surface_screen = lambda workspace_ref, surface_ref: next(screens)
        layout.wait_for_shell = lambda workspace_ref, surface_ref: None
        layout.time.sleep = lambda seconds: None
        try:
            layout.attach_surface(profile, "workspace:3", "surface:3")
        finally:
            layout.cmux = original_cmux
            layout.read_surface_screen = original_read
            layout.wait_for_shell = original_wait
            layout.time.sleep = original_sleep
        sent = [call[-1] for call in calls if call[0] == "send"]
        self.assertEqual(sent, [
            "   exec /srv/example-linux/ctx9/.local/bin/workmux linux-worker",
            "   exec /srv/example-linux/ctx9/.local/bin/workmux linux-worker",
        ])

    def test_attachment_commands_are_absolute_for_remote_machines(self):
        self.assertEqual(
            layout.attachment_command(layout.WORKSPACES[1]),
            "/srv/example-linux/ctx9/.local/bin/workmux linux-worker",
        )
        self.assertEqual(
            layout.attachment_command(layout.WORKSPACES[2]),
            "/usr/bin/env PATH=/srv/example-macos/neomk2/.local/bin:/usr/local/bin:/usr/bin:/bin "
            "/srv/example-macos/neomk2/.local/bin/workmux secondary-mac",
        )

    def test_verify_reconnect_policy_requires_helper_and_absent_agent(self):
        original_helper = layout.reconnect_helper_path
        original_agent = layout.reconnect_agent_path
        original_asset = layout.reconnect_helper_asset
        original_runtime = layout.runtime_config_path
        original_run = layout.run
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            helper = root / "workmux-cmux-attach"
            asset = root / "asset"
            agent = root / "agent.plist"
            runtime = root / "machines.json"
            asset.write_text("helper")
            helper.write_text("helper")
            helper.chmod(0o755)
            runtime.write_text(layout.runtime_config_text())
            runtime.chmod(0o600)
            layout.reconnect_helper_path = lambda: helper
            layout.reconnect_agent_path = lambda: agent
            layout.reconnect_helper_asset = lambda: asset
            layout.runtime_config_path = lambda: runtime
            layout.run = lambda *args, **kwargs: type("Result", (), {"stdout": "501\n", "returncode": 1})()
            try:
                self.assertEqual(layout.verify_reconnect_policy(), [])
                agent.write_text("old")
                self.assertIn(
                    "Primary machine: cmux workmux reconnect LaunchAgent plist still exists",
                    layout.verify_reconnect_policy(),
                )
            finally:
                layout.reconnect_helper_path = original_helper
                layout.reconnect_agent_path = original_agent
                layout.reconnect_helper_asset = original_asset
                layout.runtime_config_path = original_runtime
                layout.run = original_run

    def test_remote_creation_uses_forced_tty_and_absolute_workmux(self):
        profile = layout.WORKSPACES[1]
        created = {"windows": [{"workspaces": [workspace("workspace:9", "Migration", ["Terminal"])]}]}
        original_cmux = layout.cmux
        original_tree = layout.current_tree
        original_sleep = layout.time.sleep
        calls = []
        layout.cmux = lambda *args, **kwargs: calls.append(args)
        layout.current_tree = lambda: created
        layout.time.sleep = lambda seconds: None
        try:
            layout.create_workspace(profile, "Migration")
        finally:
            layout.cmux = original_cmux
            layout.current_tree = original_tree
            layout.time.sleep = original_sleep
        self.assertEqual(calls[0], (
            "ssh", "linux-worker", "--name", "Migration", "--no-focus",
            "--ssh-option", "RequestTTY=force", "--",
            "/srv/example-linux/ctx9/.local/bin/workmux", "linux-worker",
        ))

    def test_mac_remote_creation_supplies_managed_path(self):
        profile = layout.WORKSPACES[2]
        created = {"windows": [{"workspaces": [workspace("workspace:9", "Migration", ["Terminal"])]}]}
        original_cmux = layout.cmux
        original_tree = layout.current_tree
        original_sleep = layout.time.sleep
        calls = []
        layout.cmux = lambda *args, **kwargs: calls.append(args)
        layout.current_tree = lambda: created
        layout.time.sleep = lambda seconds: None
        try:
            layout.create_workspace(profile, "Migration")
        finally:
            layout.cmux = original_cmux
            layout.current_tree = original_tree
            layout.time.sleep = original_sleep
        self.assertEqual(calls[0][-5:], (
            "--", "/usr/bin/env", "PATH=/srv/example-macos/neomk2/.local/bin:/usr/local/bin:/usr/bin:/bin",
            "/srv/example-macos/neomk2/.local/bin/workmux", "secondary-mac",
        ))

    def test_new_remote_workspace_waits_for_health_before_metadata(self):
        profile = layout.WORKSPACES[-1]
        empty = {"windows": [{"workspaces": []}]}
        created = {
            "windows": [
                {
                    "workspaces": [
                        workspace("workspace:9", profile["title"], ["Terminal"])
                    ]
                }
            ]
        }
        original_tree = layout.current_tree
        original_create = layout.create_workspace
        original_wait_surface = layout.wait_for_managed_surface
        original_wait_session = layout.wait_for_session
        original_metadata = layout.configure_workspace_metadata
        original_attach = layout.attach_surface
        original_cmux = layout.cmux
        original_migrate = layout.migrate_remote_workspace
        calls = {"tree": 0, "waited": False, "migrated": False}

        def current_tree():
            calls["tree"] += 1
            return empty if calls["tree"] == 1 else created

        layout.current_tree = current_tree
        layout.create_workspace = lambda profile, title=None: None
        layout.wait_for_managed_surface = lambda profile, title: (
            calls.__setitem__("waited", True) or created["windows"][0]["workspaces"][0],
            created["windows"][0]["workspaces"][0]["panes"][0]["surfaces"][0],
        )
        layout.wait_for_session = lambda profile: None
        layout.configure_workspace_metadata = lambda profile, workspace_ref: None
        layout.attach_surface = lambda profile, workspace_ref, surface_ref: None
        layout.cmux = lambda *args, **kwargs: None
        layout.migrate_remote_workspace = lambda profile, workspace: calls.__setitem__(
            "migrated", True
        )
        try:
            layout.configure_profile(profile)
        finally:
            layout.current_tree = original_tree
            layout.create_workspace = original_create
            layout.wait_for_managed_surface = original_wait_surface
            layout.wait_for_session = original_wait_session
            layout.configure_workspace_metadata = original_metadata
            layout.attach_surface = original_attach
            layout.cmux = original_cmux
            layout.migrate_remote_workspace = original_migrate
        self.assertTrue(calls["waited"])
        self.assertFalse(calls["migrated"])

    def test_migration_never_closes_old_workspace_before_new_bar(self):
        profile = layout.WORKSPACES[1]
        old = workspace("workspace:2", "Linux worker", ["Terminal"])
        original_create = layout.create_workspace
        original_wait = layout.wait_for_managed_surface
        original_read = layout.read_surface_screen
        original_tree = layout.current_tree
        original_cmux = layout.cmux
        calls = []
        layout.create_workspace = lambda profile, title=None: None
        layout.wait_for_managed_surface = lambda profile, title: (_ for _ in ()).throw(RuntimeError("no bar"))
        layout.read_surface_screen = lambda workspace_ref, surface_ref: "Linux worker ~ > "
        layout.current_tree = lambda: {"windows": [{"workspaces": [old]}]}
        layout.cmux = lambda *args, **kwargs: calls.append(args)
        try:
            with self.assertRaisesRegex(RuntimeError, "no bar"):
                layout.migrate_remote_workspace(profile, old)
        finally:
            layout.create_workspace = original_create
            layout.wait_for_managed_surface = original_wait
            layout.read_surface_screen = original_read
            layout.current_tree = original_tree
            layout.cmux = original_cmux
        self.assertFalse(any(call[:2] == ("workspace", "close") for call in calls))

    def test_verify_requires_durable_remote_command_marker(self):
        tree = {"windows": [{"workspaces": [
            workspace("workspace:1", "Primary machine", ["main"], description=layout.WORKSPACES[0]["description"]),
            workspace("workspace:2", "Linux worker", ["main"], description="legacy"),
            workspace("workspace:3", "Secondary Mac", ["main"], description=layout.WORKSPACES[2]["description"]),
        ]}]}
        original_windows = layout.session_windows
        original_process = layout.session_btop_process
        original_screen = layout.read_surface_screen
        layout.session_windows = lambda profile: ["0:btop", "1:shell"]
        layout.session_btop_process = lambda profile: "btop"
        layout.read_surface_screen = lambda workspace_ref, surface_ref: "primary linux-worker secondary-mac 0:btop 1:shell CPU MEM"
        try:
            errors = layout.verify_layout(tree)
        finally:
            layout.session_windows = original_windows
            layout.session_btop_process = original_process
            layout.read_surface_screen = original_screen
        self.assertIn("Linux worker: durable remote-command marker missing", errors)

    def test_verify_rejects_btop_window_running_shell(self):
        tree = {"windows": [{"workspaces": [
            workspace("workspace:2", "Primary machine", ["main"]),
            workspace("workspace:3", "Linux worker", ["main"]),
            workspace("workspace:4", "Secondary Mac", ["main"]),
        ]}]}
        original_windows = layout.session_windows
        original_process = layout.session_btop_process
        original_screen = layout.read_surface_screen
        layout.session_windows = lambda profile: ["0:btop", "1:shell"]
        layout.session_btop_process = lambda profile: "zsh" if profile["id"] == "primary" else "btop"
        layout.read_surface_screen = lambda workspace_ref, surface_ref: "primary linux-worker secondary-mac 0:btop 1:shell CPU MEM"
        try:
            errors = layout.verify_layout(tree)
        finally:
            layout.session_windows = original_windows
            layout.session_btop_process = original_process
            layout.read_surface_screen = original_screen
        self.assertIn("Primary machine: 0:btop pane is not in managed btop/idle state", errors)

    def test_verify_accepts_hidden_btop_idle_state(self):
        tree = {"windows": [{"workspaces": [
            workspace("workspace:2", "Primary machine", ["main"]),
            workspace("workspace:3", "Linux worker", ["main"]),
            workspace("workspace:4", "Secondary Mac", ["main"]),
        ]}]}
        original_windows = layout.session_windows
        original_process = layout.session_btop_process
        original_screen = layout.read_surface_screen
        layout.session_windows = lambda profile: ["0:btop", "1:shell"]
        layout.session_btop_process = lambda profile: "sleep"
        layout.read_surface_screen = lambda workspace_ref, surface_ref: "primary linux-worker secondary-mac 0:btop 1:shell CPU MEM"
        try:
            errors = layout.verify_layout(tree)
        finally:
            layout.session_windows = original_windows
            layout.session_btop_process = original_process
            layout.read_surface_screen = original_screen
        self.assertFalse(any("btop pane" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
