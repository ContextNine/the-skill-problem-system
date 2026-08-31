#!/usr/bin/env python3
"""Tests for the phased worker Mac bootstrap."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).with_name("bootstrap_worker_mac.py")
SPEC = importlib.util.spec_from_file_location("bootstrap_worker_mac", SCRIPT)
assert SPEC and SPEC.loader
bootstrap = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bootstrap
SPEC.loader.exec_module(bootstrap)


def registry(*, enabled: bool = False, platform: str = "macos") -> dict[str, object]:
    return {
        "schema_version": 6,
        "primary_machine_id": "primary",
        "machines": [
            {
                "id": "primary",
                "display_name": "Primary",
                "enabled": True,
                "role": "primary",
                "platform": "macos",
                "transport": "local",
                "home": "/srv/example-macos/primary",
                "roots": {"code": "~/Code", "vault": "~/Vault"},
                "vault": {"enabled": True, "checkout_mode": "primary-external-git", "required": True},
                "global_agents_eligible": True,
            },
            {
                "id": "worker-mac",
                "display_name": "Worker Mac",
                "enabled": enabled,
                "role": "worker",
                "platform": platform,
                "transport": "ssh",
                "ssh_alias": "worker-mac",
                "home": "/srv/example-macos/worker",
                "global_agents_eligible": True,
                "roots": {
                    "code": "~/Code",
                    "vault": "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Vault",
                },
                "vault": {"enabled": True, "checkout_mode": "icloud-gitless", "required": True},
            },
        ],
    }


class WorkerMacBootstrapTests(unittest.TestCase):
    def test_registry_reader_accepts_future_schema_versions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / bootstrap.REGISTRY_RELATIVE
            path.parent.mkdir(parents=True)
            value = registry()
            value["schema_version"] = 99
            path.write_text(json.dumps(value), encoding="utf-8")

            self.assertEqual(bootstrap.load_registry(root)["schema_version"], 99)

    def test_resolve_requires_exact_disabled_macos_worker(self) -> None:
        machine = bootstrap.resolve_disabled_worker_mac(registry(), "worker-mac")
        self.assertEqual(machine["ssh_alias"], "worker-mac")
        self.assertEqual(bootstrap.route_alias(machine, "lan"), "worker-mac-lan")

        with self.assertRaisesRegex(bootstrap.BootstrapError, "unknown exact"):
            bootstrap.resolve_disabled_worker_mac(registry(), "Worker Mac")
        with self.assertRaisesRegex(bootstrap.BootstrapError, "requires a disabled"):
            bootstrap.resolve_disabled_worker_mac(registry(enabled=True), "worker-mac")
        with self.assertRaisesRegex(bootstrap.BootstrapError, "not a macOS worker"):
            bootstrap.resolve_disabled_worker_mac(
                registry(platform="linux"), "worker-mac"
            )

    def test_primary_host_identity_is_required(self) -> None:
        with mock.patch.object(bootstrap, "git_config", return_value="primary"):
            bootstrap.require_primary(Path("/vault"), registry())
        with mock.patch.object(bootstrap, "git_config", return_value="worker-mac"):
            with self.assertRaisesRegex(bootstrap.BootstrapError, "run worker Mac bootstrap"):
                bootstrap.require_primary(Path("/vault"), registry())

    def test_seed_dry_run_has_no_mutating_ssh_call(self) -> None:
        facts = {
            "product": "macOS",
            "version": "26.0",
            "arch": "arm64",
            "home": "/srv/example-macos/worker",
            "hostname": "worker-mac.local",
            "clt": "yes",
            "brew": "/opt/homebrew/bin/brew",
        }
        with mock.patch.object(bootstrap, "load_registry", return_value=registry()):
            with mock.patch.object(bootstrap, "require_primary"):
                with mock.patch.object(bootstrap, "remote_facts", return_value=facts):
                    with mock.patch.object(bootstrap, "ssh_run") as ssh:
                        with contextlib.redirect_stdout(io.StringIO()) as stdout:
                            result = bootstrap.command_seed(
                                Path("/vault"), "worker-mac", apply=False
                            )
        self.assertEqual(result, 0)
        self.assertIn("DRY RUN", stdout.getvalue())
        ssh.assert_not_called()

    def test_seed_stops_at_missing_local_prerequisites(self) -> None:
        facts = {
            "product": "macOS",
            "home": "/srv/example-macos/worker",
            "clt": "no",
            "brew": "",
        }
        with mock.patch.object(bootstrap, "load_registry", return_value=registry()):
            with mock.patch.object(bootstrap, "require_primary"):
                with mock.patch.object(bootstrap, "remote_facts", return_value=facts):
                    with self.assertRaises(bootstrap.ManualCheckpoint) as caught:
                        bootstrap.command_seed(Path("/vault"), "worker-mac", apply=True)
        self.assertEqual(len(caught.exception.steps), 2)
        self.assertIn("xcode-select --install", caught.exception.steps[0])
        self.assertIn("brew.sh", caught.exception.steps[1])

    def test_seed_installs_authentication_apps_without_owning_agent_configuration(self) -> None:
        script = bootstrap.seed_script("/opt/homebrew/bin/brew", "worker-mac")
        for expected in (
            "git git-lfs gh",
            "--cask bitwarden",
            "--cask chatgpt",
            "--cask google-chrome",
            "--cask codex",
            "codesign --verify --deep --strict",
            "spctl --assess --type execute",
            "vault-worker-auth-attest",
            "machineId",
            "worker-mac",
        ):
            self.assertIn(expected, script)
        self.assertNotIn("config.toml", script)

    def test_codex_worker_config_status_requires_all_three_exact_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "config.toml"
            config.write_text(
                '''approval_policy = "never"
sandbox_mode = "danger-full-access"

[mcp_servers.computer-use]
enabled = true
''',
                encoding="utf-8",
            )
            self.assertEqual(
                bootstrap.codex_worker_config_status(config),
                {
                    "approvalPolicyNever": True,
                    "dangerFullAccess": True,
                    "computerUseEnabled": True,
                },
            )
            config.write_text(
                config.read_text(encoding="utf-8").replace(
                    "enabled = true", "enabled = false"
                ),
                encoding="utf-8",
            )
            self.assertFalse(
                bootstrap.codex_worker_config_status(config)["computerUseEnabled"]
            )

    def test_auth_checkpoint_requires_user_owned_account_selection(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("ask the user to complete `Continue with Google`", source)
        self.assertIn("never infer identity from autofill", source)
        self.assertIn("never select a saved account on their behalf", source)

    def test_t3_release_selects_architecture_and_requires_digest(self) -> None:
        version = "0.0.32-nightly.20260804.998"
        tag = f"v{version}"
        payload = [
            {
                "tag_name": tag,
                "prerelease": True,
                "assets": [
                    {
                        "name": f"T3-Code-{version}-arm64.dmg",
                        "digest": "sha256:" + "a" * 64,
                        "browser_download_url": (
                            f"https://github.com/pingdotgg/t3code/releases/download/{tag}/"
                            f"T3-Code-{version}-arm64.dmg"
                        ),
                    },
                    {
                        "name": f"T3-Code-{version}-x64.dmg",
                        "digest": "sha256:" + "b" * 64,
                        "browser_download_url": (
                            f"https://github.com/pingdotgg/t3code/releases/download/{tag}/"
                            f"T3-Code-{version}-x64.dmg"
                        ),
                    },
                ],
            }
        ]
        arm = bootstrap.select_t3_release(payload, "arm64")
        intel = bootstrap.select_t3_release(payload, "x86_64")
        self.assertTrue(arm.asset_name.endswith("arm64.dmg"))
        self.assertEqual(arm.sha256, "a" * 64)
        self.assertTrue(intel.asset_name.endswith("x64.dmg"))

        payload[0]["assets"][0]["digest"] = None
        with self.assertRaisesRegex(bootstrap.BootstrapError, "valid SHA-256"):
            bootstrap.select_t3_release(payload, "arm64")

    def test_application_validation_checks_bundle_version_team_and_assessment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            app = Path(temporary) / "Example.app"
            info = app / "Contents/Info.plist"
            info.parent.mkdir(parents=True)
            info.write_bytes(
                plistlib.dumps(
                    {
                        "CFBundleIdentifier": "com.example.app",
                        "CFBundleShortVersionString": "1.2.3",
                    }
                )
            )
            with mock.patch.object(bootstrap, "app_team_id", return_value="TEAM123"):
                with mock.patch.object(bootstrap, "run") as process:
                    version = bootstrap.validate_application(
                        app,
                        bundle_id="com.example.app",
                        team_id="TEAM123",
                        expected_version="1.2.3",
                    )
        self.assertEqual(version, "1.2.3")
        self.assertEqual(process.call_count, 2)

    def test_target_identity_rejects_clone_machine_mismatch(self) -> None:
        with mock.patch.object(bootstrap.sys, "platform", "darwin"):
            with mock.patch.object(bootstrap, "load_registry", return_value=registry()):
                with mock.patch.object(bootstrap, "machine_identity", return_value="other"):
                    with self.assertRaisesRegex(bootstrap.BootstrapError, "unknown exact"):
                        bootstrap.require_target_identity(Path("/vault"))

    def test_target_identity_allows_enabled_worker_only_for_verification(self) -> None:
        with mock.patch.object(bootstrap.sys, "platform", "darwin"):
            with mock.patch.object(
                bootstrap, "load_registry", return_value=registry(enabled=True)
            ):
                with mock.patch.object(bootstrap, "machine_identity", return_value="worker-mac"):
                    with self.assertRaisesRegex(
                        bootstrap.BootstrapError, "requires a disabled"
                    ):
                        bootstrap.require_target_identity(Path("/vault"))
                    _, machine = bootstrap.require_target_identity(
                        Path("/vault"), require_disabled=False
                    )
        self.assertTrue(machine["enabled"])

    def test_command_probe_prepends_executable_directory_to_path(self) -> None:
        with mock.patch.object(
            bootstrap, "executable_path", return_value="/opt/homebrew/bin/npm"
        ):
            with mock.patch.object(
                bootstrap,
                "run",
                return_value=mock.Mock(returncode=0, stdout="11.0.0\n", stderr=""),
            ) as process:
                ok, version = bootstrap.command_exists("npm")
        self.assertTrue(ok)
        self.assertEqual(version, "11.0.0")
        command = process.call_args.args[0]
        self.assertEqual(command[0], "/usr/bin/env")
        self.assertTrue(command[1].startswith("PATH=/opt/homebrew/bin:"))

    def test_verification_requires_bitwarden_only_managed_startup(self) -> None:
        payload = {
            "commands": {"git": {"ok": True}},
            "applications": {"Bitwarden": {"ok": True}},
            "githubAuthenticated": True,
            "codexAuthenticated": True,
            "codexComputerUseEnabled": True,
            "codexBypassAllPermissions": True,
            "fileVaultOff": True,
            "automaticLoginUser": "worker",
            "automaticLoginCorrect": True,
            "automaticLogoutDisabled": True,
            "screenLockDisabled": True,
            "screenSharingLoaded": True,
            "wireGuardRunning": True,
            "wireGuardConnected": True,
            "wireGuardOnDemand": True,
            "wireGuardLoginHelperEnabled": True,
            "amphetamine": {
                "installed": True,
                "running": True,
                "startSessionAtLaunch": True,
                "indefiniteSessionConfigured": True,
                "closedDisplaySleepDisabled": True,
                "sessionActive": True,
            },
            "bitwardenRunning": True,
            "gitlessICloudCorrect": True,
            "iCloudFullyDownloaded": True,
            "refreshScheduleDisabled": True,
            "refreshScheduleBlockedPersistently": True,
            "dockedPowerOk": True,
            "batteryPowerOk": True,
            "automaticRestartEnabled": True,
            "chromeDefaultBrowser": True,
            "macStartup": {
                "loaded": True,
                "applications": ["com.bitwarden.desktop"],
            },
        }
        self.assertTrue(bootstrap.target_verification_ok(payload))
        payload["macStartup"]["applications"] = ["com.openai.codex"]
        self.assertFalse(bootstrap.target_verification_ok(payload))
        payload["macStartup"]["applications"] = ["com.bitwarden.desktop"]
        payload["amphetamine"]["closedDisplaySleepDisabled"] = False
        self.assertFalse(bootstrap.target_verification_ok(payload))
        payload["amphetamine"]["closedDisplaySleepDisabled"] = True
        payload["screenLockDisabled"] = False
        self.assertFalse(bootstrap.target_verification_ok(payload))

    def test_wireguard_status_requires_connected_on_demand_tunnel(self) -> None:
        output = """Connected
Extended Status <dictionary> {
  Status : 2
  SessionOptions : <dictionary> {
    is-on-demand : TRUE
  }
  VPN : <dictionary> {
    OnDemandAction : 1
  }
}
"""
        self.assertEqual(
            bootstrap.wireguard_status_flags(output),
            {"connected": True, "onDemand": True},
        )
        self.assertEqual(
            bootstrap.wireguard_status_flags(
                output.replace("Connected", "Disconnected", 1)
            ),
            {"connected": False, "onDemand": True},
        )
        self.assertEqual(
            bootstrap.wireguard_status_flags(
                output.replace("is-on-demand : TRUE", "is-on-demand : FALSE")
            ),
            {"connected": True, "onDemand": False},
        )

    def test_screen_lock_requires_explicit_off_state(self) -> None:
        self.assertTrue(bootstrap.screen_lock_is_disabled("screenLock is off"))
        self.assertFalse(
            bootstrap.screen_lock_is_disabled("screenLock delay is 0 seconds")
        )

    def test_amphetamine_preferences_require_closed_display_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            preferences = Path(temporary) / "amphetamine.plist"
            preferences.write_bytes(
                plistlib.dumps(
                    {
                        "Start Session At Launch": True,
                        "Default Duration": 0,
                        "Allow Closed-Display Sleep": False,
                    }
                )
            )
            self.assertEqual(
                bootstrap.amphetamine_preference_flags(preferences),
                {
                    "startSessionAtLaunch": True,
                    "indefiniteSessionConfigured": True,
                    "closedDisplaySleepDisabled": True,
                },
            )
            preferences.write_bytes(
                plistlib.dumps(
                    {
                        "Start Session At Launch": True,
                        "Default Duration": 0,
                        "Allow Closed-Display Sleep": True,
                    }
                )
            )
            self.assertFalse(
                bootstrap.amphetamine_preference_flags(preferences)[
                    "closedDisplaySleepDisabled"
                ]
            )

    def test_amphetamine_assertion_requires_active_system_session(self) -> None:
        self.assertTrue(
            bootstrap.amphetamine_assertion_active(
                'pid 6936(Amphetamine): PreventUserIdleSystemSleep named: "Amphetamine (Single-Use - System)"'
            )
        )
        self.assertFalse(
            bootstrap.amphetamine_assertion_active(
                'pid 6936(Amphetamine): PreventUserIdleDisplaySleep named: "Amphetamine (Single-Use - Display)"'
            )
        )

    def test_default_browser_handlers_require_chrome_for_http_and_https(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            preferences = Path(temporary) / "launch-services.plist"
            preferences.write_bytes(
                plistlib.dumps(
                    {
                        "LSHandlers": [
                            {
                                "LSHandlerURLScheme": "http",
                                "LSHandlerRoleAll": "com.google.Chrome",
                            },
                            {
                                "LSHandlerURLScheme": "https",
                                "LSHandlerRoleAll": "com.google.Chrome",
                            },
                        ]
                    }
                )
            )
            handlers = bootstrap.default_browser_handlers(preferences)
        self.assertEqual(
            handlers,
            {"http": "com.google.chrome", "https": "com.google.chrome"},
        )

    def test_automatic_restart_reads_power_management_plist(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            preferences = Path(temporary) / "power.plist"
            payload = {
                source: {"Automatic Restart On Power Loss": 1}
                for source in ("AC Power", "Battery Power")
            }
            preferences.write_bytes(plistlib.dumps(payload))
            self.assertTrue(bootstrap.automatic_restart_enabled(preferences))
            payload["Battery Power"]["Automatic Restart On Power Loss"] = 0
            preferences.write_bytes(plistlib.dumps(payload))
            self.assertFalse(bootstrap.automatic_restart_enabled(preferences))

    def test_local_auth_attestation_is_machine_scoped_and_private(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            attestation = Path(temporary) / "auth-attestation.json"
            attestation.write_text(
                json.dumps(
                    {
                        "machineId": "worker-mac",
                        "githubAuthenticated": True,
                        "githubProtocolSsh": True,
                        "githubSshAuthenticated": True,
                        "codexAuthenticated": True,
                    }
                )
            )
            attestation.chmod(0o600)
            self.assertEqual(
                bootstrap.local_auth_attestation("worker-mac", attestation),
                {"githubAuthenticated": True, "codexAuthenticated": True},
            )
            self.assertFalse(
                bootstrap.local_auth_attestation("another-machine", attestation)[
                    "githubAuthenticated"
                ]
            )
            attestation.chmod(0o644)
            self.assertFalse(
                bootstrap.local_auth_attestation("worker-mac", attestation)[
                    "codexAuthenticated"
                ]
            )

    def test_pmset_parser_reads_only_ac_policy(self) -> None:
        output = """Battery Power:
 sleep 3
 womp 0
AC Power:
 displaysleep 30
 womp 1
 autorestart 1
 sleep 0
"""
        self.assertEqual(
            bootstrap.pmset_ac_settings(output),
            {
                "displaysleep": "30",
                "womp": "1",
                "autorestart": "1",
                "sleep": "0",
            },
        )

    def test_source_never_accepts_password_or_token_arguments(self) -> None:
        parser = bootstrap.build_parser()
        actions = {action.dest for action in parser._actions}
        self.assertNotIn("password", actions)
        self.assertNotIn("token", actions)
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("--password", source)
        self.assertNotIn("--token", source)


if __name__ == "__main__":
    unittest.main()
