from __future__ import annotations

import importlib.machinery
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("configure_warp_machine_workspaces.py")
SPEC = importlib.util.spec_from_file_location("configure_warp_machine_workspaces", SCRIPT)
assert SPEC and SPEC.loader
warp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(warp)

HELPER = Path(__file__).parent.parent / "assets/terminal-workspaces/workmux-warp-attach"
LOADER = importlib.machinery.SourceFileLoader("workmux_warp_attach", str(HELPER))
HELPER_SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
assert HELPER_SPEC
attach = importlib.util.module_from_spec(HELPER_SPEC)
LOADER.exec_module(attach)

STARTUP = Path(__file__).parent.parent / "assets/terminal-workspaces/workmux-warp-startup"
STARTUP_LOADER = importlib.machinery.SourceFileLoader("workmux_warp_startup", str(STARTUP))
STARTUP_SPEC = importlib.util.spec_from_loader(STARTUP_LOADER.name, STARTUP_LOADER)
assert STARTUP_SPEC
startup = importlib.util.module_from_spec(STARTUP_SPEC)
STARTUP_LOADER.exec_module(startup)

warp.TERMINAL_PROFILES = [
    {"id": "primary", "title": "Primary machine", "transport": "local", "warp_color": "red"},
    {"id": "linux-worker", "title": "Linux worker", "transport": "ssh", "warp_color": "blue"},
    {"id": "secondary-mac", "title": "Secondary Mac", "transport": "ssh", "warp_color": "green"},
    {"id": "worker-mac", "title": "Worker Mac", "transport": "ssh", "warp_color": "magenta"},
]
warp.MANAGED_MARKERS = tuple(profile["id"] for profile in warp.TERMINAL_PROFILES)
warp.LEGACY_HELPERS = ("warp-linux-worker-main",)
warp.LEGACY_MARKERS = ("home", "workspace", "impression")
attach.PROFILES = {
    "linux-worker": {"name": "Linux worker", "ssh_alias": "linux-worker", "remote_command": ["/srv/example-linux/ctx9/.local/bin/workmux", "linux-worker"]},
    "secondary-mac": {"name": "Secondary Mac", "ssh_alias": "secondary-mac", "remote_command": ["/usr/bin/env", "PATH=/srv/example-macos/neomk2/.local/bin:/usr/local/bin:/usr/bin:/bin", "/srv/example-macos/neomk2/.local/bin/workmux", "secondary-mac"]},
    "worker-mac": {"name": "Worker Mac", "ssh_alias": "worker-mac", "remote_command": ["/usr/bin/env", "PATH=/srv/example-macos/ctx9/.local/bin:/opt/homebrew/bin:/usr/bin:/bin", "/srv/example-macos/ctx9/.local/bin/workmux", "worker-mac"]},
}


class ConfigureWarpTests(unittest.TestCase):
    def prepare_home(self, root: Path) -> None:
        settings = warp.settings_path(root)
        settings.parent.mkdir(parents=True)
        settings.write_text("[appearance.vertical_tabs]\nenabled = true\n")
        main = warp.main_config_path(root)
        main.parent.mkdir(parents=True, exist_ok=True)
        main.write_text("name: preserved\n")

    def test_rendered_config_has_registered_tabs_and_commands(self):
        root = Path("/srv/example-macos/tester")
        rendered = warp.render_config(root)
        self.assertEqual(rendered.count("      - title:"), 4)
        for title in (
            "Primary machine \u00b7 main",
            "Linux worker \u00b7 main",
            "Secondary Mac \u00b7 main",
            "Worker Mac \u00b7 main",
        ):
            self.assertIn(title, rendered)
        for title in ("Primary machine \u00b7 Home", "Primary machine \u00b7 Workspace", "Primary machine \u00b7 Impression"):
            self.assertNotIn(title, rendered)
        self.assertIn("active_tab_index: 0", rendered)
        self.assertIn("/srv/example-macos/tester/.local/bin/workmux primary", rendered)
        self.assertIn("/srv/example-macos/tester/.local/bin/workmux-warp-attach linux-worker", rendered)
        self.assertIn("/srv/example-macos/tester/.local/bin/workmux-warp-attach secondary-mac", rendered)
        self.assertIn(
            "/srv/example-macos/tester/.local/bin/workmux-warp-attach worker-mac", rendered
        )

    def test_registry_rejects_unknown_warp_color(self):
        with self.assertRaisesRegex(ValueError, "invalid Warp color"):
            warp.validate_profiles([{"id": "worker", "warp_color": "purple"}])

    def test_ssh_commands_use_aliases_forced_tty_and_exact_workmux(self):
        linux_worker = attach.ssh_command(attach.PROFILES["linux-worker"])
        mini = attach.ssh_command(attach.PROFILES["secondary-mac"])
        self.assertEqual(linux_worker[0:2], ["/usr/bin/ssh", "-tt"])
        self.assertIn("linux-worker", linux_worker)
        self.assertEqual(linux_worker[-2:], ["/srv/example-linux/ctx9/.local/bin/workmux", "linux-worker"])
        self.assertIn("secondary-mac", mini)
        self.assertEqual(mini[-4:], [
            "/usr/bin/env",
            "PATH=/srv/example-macos/neomk2/.local/bin:/usr/local/bin:/usr/bin:/bin",
            "/srv/example-macos/neomk2/.local/bin/workmux",
            "secondary-mac",
        ])
        worker = attach.ssh_command(attach.PROFILES["worker-mac"])
        self.assertEqual(worker[-4:], [
            "/usr/bin/env",
            "PATH=/srv/example-macos/ctx9/.local/bin:/opt/homebrew/bin:/usr/bin:/bin",
            "/srv/example-macos/ctx9/.local/bin/workmux",
            "worker-mac",
        ])

    def test_only_transport_failure_retries(self):
        self.assertTrue(attach.should_retry(255))
        self.assertFalse(attach.should_retry(0))
        self.assertFalse(attach.should_retry(1))
        self.assertFalse(attach.should_retry(130))

    def test_apply_preserves_main_config_and_archives_legacy_helpers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.prepare_home(root)
            original_main = warp.main_config_path(root).read_bytes()
            legacy = root / ".local/bin/warp-linux-worker-main"
            legacy.parent.mkdir(parents=True)
            legacy.write_text("old\n")
            backups, notices = warp.apply(root)
            self.assertEqual(warp.main_config_path(root).read_bytes(), original_main)
            self.assertFalse(legacy.exists())
            self.assertTrue(any(str(path).startswith(str(legacy) + ".backup-") for path in backups))
            self.assertEqual(notices, [])
            self.assertEqual(warp.differences(root), [])

    def test_apply_preserves_user_tab_configs_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.prepare_home(root)
            tab_config = root / ".warp/tab_configs/my-project.toml"
            tab_config.parent.mkdir(parents=True)
            original = b'name = "My project"\n# user-owned\n'
            tab_config.write_bytes(original)
            warp.apply(root)
            self.assertEqual(tab_config.read_bytes(), original)

    def test_apply_removes_only_empty_legacy_marker_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.prepare_home(root)
            markers = warp.marker_root(root)
            (markers / "home").mkdir(parents=True)
            (markers / "workspace").mkdir()
            (markers / "workspace/keep.txt").write_text("keep\n")
            _backups, notices = warp.apply(root)
            self.assertFalse((markers / "home").exists())
            self.assertTrue((markers / "workspace/keep.txt").exists())
            self.assertEqual(notices, [f"preserved non-empty directory {markers / 'workspace'}"])

    def test_apply_preserves_unrelated_zshrc_and_adds_one_startup_block(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.prepare_home(root)
            warp.zshrc_path(root).write_text("export KEEP_THIS=yes\n")
            warp.apply(root)
            rendered = warp.zshrc_path(root).read_text()
            self.assertIn("export KEEP_THIS=yes", rendered)
            self.assertEqual(rendered.count(warp.RC_BEGIN), 1)
            self.assertEqual(rendered.count(warp.RC_END), 1)
            warp.apply(root)
            self.assertEqual(warp.zshrc_path(root).read_text(), rendered)

    def test_apply_disables_session_restore_and_preserves_unrelated_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.prepare_home(root)
            settings = warp.settings_path(root)
            settings.write_text(
                "[appearance.vertical_tabs]\nenabled = true\n\n"
                "[general]\nkeep_this = true\n\n"
                "[appearance.text]\nfont_size = 14\n"
            )
            warp.apply(root)
            rendered = settings.read_text()
            self.assertIn("keep_this = true", rendered)
            self.assertIn("font_size = 14", rendered)
            self.assertIn("restore_session = false", rendered)
            self.assertTrue(warp.session_restore_disabled(settings))

    def test_startup_skips_launch_configuration_marker_directory(self):
        root = Path("/srv/example-macos/tester")
        result = startup.run(123, startup.marker_root(root) / "primary", root)
        self.assertEqual(result, "managed-launch-pane")

    def test_startup_requires_all_enabled_remote_profiles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / ".config/workmux/machines.json"
            runtime.parent.mkdir(parents=True)
            runtime.write_text(
                json.dumps(
                    {
                        "machines": [
                            {
                                "id": "primary",
                                "enabled": True,
                                "transport": "local",
                                "terminal_profile": {},
                            },
                            {
                                "id": "worker-a",
                                "enabled": True,
                                "transport": "ssh",
                                "terminal_profile": {},
                            },
                            {
                                "id": "worker-b",
                                "enabled": False,
                                "transport": "ssh",
                                "terminal_profile": {},
                            },
                        ]
                    }
                )
            )
            self.assertEqual(
                startup.managed_remote_machine_ids(root), ("worker-a",)
            )

    def test_startup_opens_once_for_warp_process(self):
        processes = {
            300: (200, "/bin/zsh -l"),
            200: (100, "/Applications/Warp.app/Contents/MacOS/stable terminal-server --parent-pid=100"),
            100: (1, startup.WARP_EXECUTABLE),
        }
        opened: list[bool] = []
        closed: list[tuple[int, int]] = []
        helper_states = iter((False, True))
        with tempfile.TemporaryDirectory() as directory:
            kwargs = dict(
                reader=processes.get,
                start_reader=lambda _pid: "Wed Jul 22 18:00:00 2026",
                sleeper=lambda _seconds: None,
                helper_check=lambda: next(helper_states),
                opener=lambda: opened.append(True),
                closer=lambda shell_pid, warp_pid: closed.append((shell_pid, warp_pid)),
                lock_root=Path(directory),
            )
            first = startup.run(300, Path("/srv/example-macos/tester"), Path("/srv/example-macos/tester"), **kwargs)
            second = startup.run(300, Path("/srv/example-macos/tester"), Path("/srv/example-macos/tester"), **kwargs)
        self.assertEqual(first, "opened")
        self.assertEqual(second, "already-claimed")
        self.assertEqual(opened, [True])
        self.assertEqual(closed, [(300, 100)])

    def test_startup_polls_for_delayed_helpers_before_closing(self):
        processes = {20: (10, "/bin/zsh"), 10: (1, startup.WARP_EXECUTABLE)}
        helper_states = iter((False, False, False, True))
        sleeps: list[float] = []
        closed: list[tuple[int, int]] = []
        with tempfile.TemporaryDirectory() as directory:
            result = startup.run(
                20,
                Path("/srv/example-macos/tester"),
                Path("/srv/example-macos/tester"),
                reader=processes.get,
                start_reader=lambda _pid: "start",
                sleeper=sleeps.append,
                helper_check=lambda: next(helper_states),
                opener=lambda: None,
                closer=lambda shell_pid, warp_pid: closed.append((shell_pid, warp_pid)),
                lock_root=Path(directory),
            )
        self.assertEqual(result, "opened")
        self.assertEqual(sleeps, [startup.WAIT_SECONDS, startup.CLOSE_POLL_SECONDS, startup.CLOSE_POLL_SECONDS])
        self.assertEqual(closed, [(20, 10)])

    def test_startup_leaves_origin_open_when_helpers_time_out(self):
        processes = {20: (10, "/bin/zsh"), 10: (1, startup.WARP_EXECUTABLE)}
        closed: list[tuple[int, int]] = []
        with tempfile.TemporaryDirectory() as directory:
            result = startup.run(
                20,
                Path("/srv/example-macos/tester"),
                Path("/srv/example-macos/tester"),
                reader=processes.get,
                start_reader=lambda _pid: "start",
                sleeper=lambda _seconds: None,
                helper_check=lambda: False,
                opener=lambda: None,
                closer=lambda shell_pid, warp_pid: closed.append((shell_pid, warp_pid)),
                lock_root=Path(directory),
            )
        self.assertEqual(result, "opened")
        self.assertEqual(closed, [])

    def test_startup_does_not_duplicate_running_workspace(self):
        processes = {20: (10, "/bin/zsh"), 10: (1, startup.WARP_EXECUTABLE)}
        with tempfile.TemporaryDirectory() as directory:
            result = startup.run(
                20,
                Path("/srv/example-macos/tester"),
                Path("/srv/example-macos/tester"),
                reader=processes.get,
                start_reader=lambda _pid: "start",
                sleeper=lambda _seconds: None,
                helper_check=lambda: True,
                opener=lambda: self.fail("must not open duplicate workspace"),
                lock_root=Path(directory),
            )
        self.assertEqual(result, "already-running")

    def test_verify_reports_disabled_vertical_tabs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.prepare_home(root)
            warp.apply(root)
            warp.settings_path(root).write_text("[appearance.vertical_tabs]\nenabled = false\n")
            self.assertIn("Warp vertical tabs are not enabled", warp.differences(root))


if __name__ == "__main__":
    unittest.main()
