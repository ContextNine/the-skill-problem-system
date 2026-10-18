from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from unittest import mock


SCRIPT = Path(__file__).with_name("setup_tailscale_access.py")
SPEC = importlib.util.spec_from_file_location("setup_tailscale_access", SCRIPT)
assert SPEC and SPEC.loader
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)


class SetupTailscaleAccessTests(unittest.TestCase):
    def test_latest_macos_package_uses_highest_stable_version(self):
        html = (
            '<a href="Tailscale-1.99.9-macos.pkg">old</a>'
            '<a href="Tailscale-1.102.3-macos.pkg">new</a>'
        )
        self.assertEqual(
            setup.latest_macos_pkg_url(html),
            "https://pkgs.tailscale.com/stable/Tailscale-1.102.3-macos.pkg",
        )

    def test_registry_settings_require_explicit_safe_desired_state(self):
        machine = {
            "id": "worker",
            "platform": "linux",
            "machine_access": {
                "providers": {
                    "tailscale": {
                        "client_variant": "linux-package",
                        "desired_state": {
                            "device_name": "worker",
                            "accept_dns": True,
                            "accept_routes": False,
                            "tailscale_ssh": False,
                        },
                    }
                }
            },
        }
        self.assertEqual(
            setup.tailscale_settings(machine),
            (
                "worker",
                "linux-package",
                {
                    "device_name": "worker",
                    "accept_dns": True,
                    "accept_routes": False,
                    "tailscale_ssh": False,
                },
            ),
        )

    def test_desired_command_keeps_tailscale_ssh_and_routes_disabled(self):
        machine = {"platform": "linux"}
        desired = {
            "device_name": "worker",
            "accept_dns": True,
            "accept_routes": False,
            "tailscale_ssh": False,
        }
        self.assertEqual(
            setup.desired_up_argv(machine, desired),
            [
                "sudo",
                "-n",
                "tailscale",
                "up",
                "--hostname=worker",
                "--accept-dns=true",
                "--accept-routes=false",
                "--ssh=false",
                "--timeout=10s",
            ],
        )

    def test_auth_url_retains_only_the_login_checkpoint(self):
        output = "To authenticate, visit:\nhttps://login.tailscale.com/a/abc_123\n"
        self.assertEqual(setup.auth_url(output), "https://login.tailscale.com/a/abc_123")

    def test_app_store_selection_never_stages_standalone_variant(self):
        machine = {"platform": "macos", "transport": "local"}
        with mock.patch.object(setup, "target_has", return_value=False), mock.patch.object(
            setup, "stage_macos_installer"
        ) as stage:
            installed, checkpoint, evidence = setup.install_if_needed(machine, "app-store", True)
        self.assertFalse(installed)
        self.assertIn("App Store", checkpoint)
        self.assertEqual(evidence, {})
        stage.assert_not_called()

    def test_remote_macos_stage_falls_back_to_verified_target_download(self):
        machine = {"ssh_alias": "worker"}
        completed = mock.Mock(returncode=0, stdout="", stderr="")
        target_calls = [
            mock.Mock(returncode=1, stdout="", stderr="missing"),
            completed,
            mock.Mock(returncode=0, stdout="abc123  package.download\n", stderr=""),
            completed,
            mock.Mock(returncode=0, stdout="abc123  package.pkg\n", stderr=""),
        ]
        with mock.patch.object(
            setup.subprocess,
            "run",
            side_effect=setup.subprocess.TimeoutExpired(["scp"], 120),
        ), mock.patch.object(setup, "run_target", side_effect=target_calls) as run_target:
            setup.stage_remote_macos_pkg(
                machine,
                Path("/tmp/package.pkg"),
                "https://pkgs.tailscale.com/stable/package.pkg",
                "/tmp/package.pkg",
                "abc123",
            )

        self.assertEqual(run_target.call_count, 5)
        self.assertEqual(run_target.call_args_list[1].args[1][0], "/usr/bin/curl")
        self.assertEqual(run_target.call_args_list[2].args[1][-1], "/tmp/package.pkg.download")
        self.assertEqual(run_target.call_args_list[3].args[1], ["mv", "-f", "/tmp/package.pkg.download", "/tmp/package.pkg"])


if __name__ == "__main__":
    unittest.main()
