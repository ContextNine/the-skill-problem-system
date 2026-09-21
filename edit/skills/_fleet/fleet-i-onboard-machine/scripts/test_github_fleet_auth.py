#!/usr/bin/env python3
"""Focused tests for fleet GitHub authentication."""

from __future__ import annotations

import base64
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock


SCRIPT = Path(__file__).with_name("github_fleet_auth.py")
SPEC = importlib.util.spec_from_file_location("github_fleet_auth", SCRIPT)
assert SPEC and SPEC.loader
auth = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = auth
SPEC.loader.exec_module(auth)


class GithubFleetAuthTests(unittest.TestCase):
    def test_preview_is_read_only(self) -> None:
        machine = {"id": "worker", "transport": "local"}
        with mock.patch.object(auth, "github_keys", return_value=[]):
            with mock.patch.object(
                auth,
                "audit_machine",
                return_value={"machine_id": "worker", "private_key": True},
            ):
                with mock.patch.object(auth, "target_run") as target_run:
                    self.assertEqual(
                        auth.command_provision([machine], apply=False, interactive=False), 0
                    )
        target_run.assert_not_called()

    def test_enrollment_is_idempotent_by_fingerprint(self) -> None:
        key_blob = base64.b64encode(b"test-public-key").decode()
        key = f"ssh-ed25519 {key_blob} ctx9-fleet:worker"
        fingerprint = auth.public_key_fingerprint(key)
        machine = {"id": "worker", "transport": "local"}
        with mock.patch.object(auth, "public_key", return_value=key):
            with mock.patch.object(
                auth,
                "github_keys",
                return_value=[{"fingerprint": fingerprint, "title": "ctx9-fleet:worker"}],
            ):
                with mock.patch.object(auth, "run") as process:
                    self.assertEqual(
                        auth.command_enroll(
                            [machine], apply=True, approve_fingerprint=fingerprint
                        ),
                        0,
                    )
        process.assert_not_called()

    def test_audit_never_reads_or_prints_private_key_material(self) -> None:
        source = auth.audit_script("worker")
        self.assertNotIn("cat \"$key\"", source)
        self.assertNotIn("base64", source)
        self.assertIn("ssh-keygen -lf \"$key.pub\"", source)
        self.assertIn("ssh -n -o BatchMode=yes", source)

    def test_audit_discovers_macos_gui_agent_and_homebrew_gh(self) -> None:
        source = auth.audit_script("worker")
        self.assertIn("gui/$(id -u)/com.openssh.ssh-agent", source)
        self.assertIn('/opt/homebrew/bin:/usr/local/bin:$PATH', source)
        self.assertIn('export SSH_AUTH_SOCK="$native_agent"', source)

    def test_audit_connects_linux_gh_to_the_user_dbus(self) -> None:
        source = auth.audit_script("worker")
        self.assertIn("XDG_RUNTIME_DIR", source)
        self.assertIn("DBUS_SESSION_BUS_ADDRESS", source)

    def test_audit_accepts_secret_free_worker_mac_gui_attestation(self) -> None:
        source = auth.audit_script("worker")
        self.assertIn("auth-attestation.json", source)
        self.assertIn("githubAuthenticated", source)
        self.assertIn("gui_gh_attestation", source)

    def test_apply_stops_before_mutation_when_key_is_missing(self) -> None:
        machine = {"id": "worker", "transport": "local"}
        with mock.patch.object(auth, "github_keys", return_value=[]):
            with mock.patch.object(
                auth,
                "audit_machine",
                return_value={"machine_id": "worker", "private_key": False},
            ):
                with mock.patch.object(auth, "target_run") as target_run:
                    with self.assertRaisesRegex(auth.FleetAuthError, "interactive"):
                        auth.command_provision(
                            [machine], apply=True, interactive=False
                        )
        target_run.assert_not_called()

    def test_passphrase_free_preview_is_read_only(self) -> None:
        machine = {"id": "worker", "transport": "local"}
        report = {
            "machine_id": "worker",
            "platform": "Linux",
            "private_key": True,
            "passphrase_free_key": False,
            "github_enrolled": False,
        }
        with mock.patch.object(auth, "github_keys", return_value=[]):
            with mock.patch.object(auth, "audit_machine", return_value=report):
                with mock.patch.object(auth, "target_run") as target_run:
                    self.assertEqual(
                        auth.command_provision(
                            [machine],
                            apply=False,
                            interactive=False,
                            allow_passphrase_free=True,
                        ),
                        0,
                    )
        target_run.assert_not_called()

    def test_passphrase_free_generation_preserves_prior_pair(self) -> None:
        source = auth.passphrase_free_generation_script("worker")
        self.assertIn("ctx9-key-backups", source)
        self.assertIn('mv "$key" "$backup/"', source)
        self.assertIn("-N ''", source)

    def test_linux_exception_satisfies_custody_gate(self) -> None:
        report = {
            "machine_id": "worker",
            "reachable": True,
            "platform": "Linux",
            "private_key": True,
            "public_key": True,
            "managed_config": True,
            "effective_identity": True,
            "github_host_key": True,
            "native_agent": False,
            "agent_visible": False,
            "passphrase_free_exception": True,
            "passphrase_free_key": True,
            "gh_api": True,
            "github_ssh": True,
            "github_enrolled": True,
            "gh_protocol": "ssh",
            "plaintext_oauth": False,
        }
        with mock.patch.object(auth, "github_keys", return_value=[]):
            with mock.patch.object(auth, "audit_machine", return_value=report):
                self.assertEqual(auth.command_verify([{"id": "worker"}], json_output=False), 0)
        self.assertTrue(report["accepted"])


if __name__ == "__main__":
    unittest.main()
