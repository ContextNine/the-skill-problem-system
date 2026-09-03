from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("sync_terminal_profiles.py")
SPEC = importlib.util.spec_from_file_location("sync_terminal_profiles", SCRIPT)
assert SPEC and SPEC.loader
sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync)

sync.PROFILES = {
    "primary": {"name": "Primary machine", "accent": "#AD1457"},
    "linux-worker": {"name": "Linux worker", "accent": "#1565C0"},
    "secondary-mac": {
        "name": "Secondary Mac",
        "accent": "#2E7D32",
        "link_brew_commands": ("tmux",),
        "starship_prebuilt": {
            "version": "1.26.0",
            "url": "https://example.invalid/starship-x86_64-apple-darwin.tar.gz",
            "sha256": "a" * 64,
        },
        "btop_prebuilt": {
            "version": "1.3.2",
            "url": "https://ghcr.io/v2/homebrew/core/btop/blobs/example",
            "gcc_sha256": "b" * 64,
        },
    },
}


class SyncTerminalProfilesTests(unittest.TestCase):
    def inventory(self):
        return {
            "schema_version": 6,
            "machines": [
                {"id": "primary", "display_name": "Primary machine", "enabled": True, "transport": "local", "home": "/srv/example-macos/matt"},
                {"id": "linux-worker", "display_name": "Linux worker", "enabled": True, "transport": "ssh", "ssh_alias": "linux-worker", "home": "/srv/example-linux/matt"},
                {"id": "secondary-mac", "display_name": "Secondary Mac", "enabled": False, "transport": "ssh", "ssh_alias": "mini", "home": "/srv/example-macos/mini"},
            ],
        }

    def test_inventory_selection_and_disabled_target(self):
        self.assertEqual([m["id"] for m in sync.select_devices(self.inventory())], ["primary", "linux-worker"])
        self.assertEqual(sync.select_devices(self.inventory(), {"Linux worker"})[0]["id"], "linux-worker")
        with self.assertRaisesRegex(ValueError, "disabled"):
            sync.select_devices(self.inventory(), {"Secondary Mac"})
        self.assertEqual(
            sync.select_devices(
                self.inventory(), {"Secondary Mac"}, provision_disabled=True
            )[0]["id"],
            "secondary-mac",
        )
        with self.assertRaisesRegex(ValueError, "explicit --target"):
            sync.select_devices(self.inventory(), provision_disabled=True)

    def test_inventory_file_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "machines.json"
            path.write_text(json.dumps(self.inventory()))
            self.assertEqual(sync.load_inventory(path)["schema_version"], 6)

    def test_rendered_machine_colors_and_sessions(self):
        template = "__MACHINE_NAME__ __ACCENT__"
        self.assertEqual(sync.render_starship("primary", template), "Primary machine #AD1457")
        self.assertEqual(sync.render_workmux("secondary-mac", "x=__DEFAULT_SESSION__"), "x=secondary-mac")

    def test_btop_control_is_session_scoped_and_refreshes_each_second(self):
        assets = sync.skill_root() / "assets/terminal-workspaces"
        control = sync.render_workmux("linux-worker", (assets / "workmux-btop-control").read_text())
        workmux = sync.render_workmux("linux-worker", (assets / "workmux").read_text())
        tmux = (assets / "tmux.conf").read_text()
        self.assertIn("managed_session=linux-worker", control)
        self.assertIn("#{window_active_clients}", control)
        self.assertIn("sleep_bin=$(command -v sleep", control)
        self.assertIn("2147483647", control)
        self.assertNotIn("kill -STOP", control)
        self.assertIn("respawn-pane -k", control)
        self.assertEqual(workmux.count("--update 1000"), 3)
        self.assertIn("btop|sleep", workmux)
        self.assertIn("after-select-window", tmux)
        self.assertIn("bind n select-window -n", tmux)
        self.assertIn("bind p select-window -p", tmux)
        self.assertIn("bind l select-window -l", tmux)
        self.assertIn("client-attached", tmux)
        self.assertIn("client-detached", tmux)
        self.assertEqual(tmux.count("/bin/sleep 0.1;"), 3)

    def test_starship_template_is_simple_single_line_custom_module(self):
        template = (sync.skill_root() / "assets/terminal-workspaces/starship.toml.template").read_text()
        self.assertIn('${custom.machine}$directory$git_branch$git_status$time$character', template)
        self.assertNotIn('\\n$character', template)
        self.assertIn('[time]\ndisabled = false', template)
        self.assertIn('time_format = "%d/%m %H:%M"', template)
        self.assertIn('utc_time_offset = "2"', template)
        self.assertIn('style = "dimmed white"', template)

    def test_shell_marker_is_idempotent(self):
        initial = "export EDITOR=vim\n"
        once = sync.update_marker(initial, "zsh")
        twice = sync.update_marker(once, "zsh")
        self.assertEqual(once, twice)
        self.assertEqual(once.count(sync.MARKER_START), 1)
        self.assertIn("starship init zsh", once)

        marker_only = sync.update_marker("", "zsh")
        self.assertEqual(sync.update_marker(marker_only, "zsh"), marker_only)
        self.assertFalse(marker_only.startswith("\n"))

    def test_local_atomic_deploy_creates_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "config"
            target.write_text("old")
            host = sync.Host({"id": "test", "transport": "local", "home": directory})
            host.deploy(str(target), b"new", 0o600, "STAMP")
            self.assertEqual(target.read_text(), "new")
            self.assertEqual(Path(str(target) + ".backup-STAMP").read_text(), "old")

    def test_plugin_pins_are_exact(self):
        self.assertEqual(sync.PLUGIN_PINS["tmux-resurrect"][1], "cff343cf9e81983d3da0c8562b01616f12e8d548")
        self.assertEqual(sync.PLUGIN_PINS["tmux-continuum"][1], "0698e8f4b17d6454c71bf5212895ec055c578da0")
        self.assertEqual(sync.PLUGIN_PINS["tmux-cpu"][1], "bcb110d754ab2417de824c464730c412a3eb2769")

    def test_mac_mini_uses_pinned_prebuilt_starship(self):
        profile = sync.PROFILES["secondary-mac"]
        release = profile["starship_prebuilt"]
        self.assertEqual(profile["link_brew_commands"], ("tmux",))
        self.assertEqual(release["version"], "1.26.0")
        self.assertIn("starship-x86_64-apple-darwin.tar.gz", release["url"])
        self.assertEqual(len(release["sha256"]), 64)
        btop = profile["btop_prebuilt"]
        self.assertEqual(btop["version"], "1.3.2")
        self.assertIn("ghcr.io/v2/homebrew/core/btop", btop["url"])
        self.assertEqual(len(btop["gcc_sha256"]), 64)

    def test_dry_run_mode_is_default(self):
        args = sync.parser().parse_args([])
        self.assertFalse(args.apply)
        self.assertFalse(args.verify)


if __name__ == "__main__":
    unittest.main()
