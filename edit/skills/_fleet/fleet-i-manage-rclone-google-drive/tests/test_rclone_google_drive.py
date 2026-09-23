from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, call, patch


SCRIPT = Path(__file__).parents[1] / "scripts/rclone_google_drive.py"
SPEC = importlib.util.spec_from_file_location("rclone_google_drive", SCRIPT)
assert SPEC and SPEC.loader
rclone_google_drive = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rclone_google_drive)


def desired(enabled: bool = True) -> dict[str, object]:
    return {
        "schema_version": 2,
        "enabled": enabled,
        "remote_name": "ctx9_codefoldersync_backups",
        "allowed_machines": ["primary-mac", "worker-linux", "worker-mac"],
        "google_drive": {
            "oauth_client_id_binding": "GOOGLE_PERSONAL_OAUTH_CLIENT_ID",
            "oauth_client_secret_binding": "GOOGLE_PERSONAL_OAUTH_CLIENT_SECRET",
            "scope": "drive.file",
            "shared_drive_id": "shared-drive-id",
            "root_folder_id": "root-folder-id",
        },
        "paths": {
            "backup_prefix": "CodeFolderSync Backups",
            "acceptance_prefix": ".ctx9-acceptance",
        },
        "retention": {"mode": "explicit-retirement-only", "automatic_deletion": False},
    }


class DesiredStateTests(unittest.TestCase):
    def test_classifies_rclone_errors_without_returning_provider_text(self) -> None:
        message = "provider request contains private-id: directory not found"
        self.assertEqual(rclone_google_drive.classify_rclone_failure(message), "not_found")

    def test_requires_drive_file_and_no_automatic_deletion(self) -> None:
        value = desired()
        value["google_drive"]["scope"] = "drive"  # type: ignore[index]
        with self.assertRaisesRegex(rclone_google_drive.BackupError, "drive.file"):
            rclone_google_drive.validate_desired(value)

        value = desired()
        value["retention"]["automatic_deletion"] = True  # type: ignore[index]
        with self.assertRaisesRegex(rclone_google_drive.BackupError, "forbidden"):
            rclone_google_drive.validate_desired(value)

    def test_disabled_placeholder_state_has_explicit_gates(self) -> None:
        value = desired(enabled=False)
        value["allowed_machines"] = []
        value["google_drive"]["shared_drive_id"] = None  # type: ignore[index]
        value["google_drive"]["root_folder_id"] = None  # type: ignore[index]
        self.assertEqual(
            rclone_google_drive.desired_missing(rclone_google_drive.validate_desired(value)),
            [
                "enabled",
                "allowed_machines",
                "google_drive.shared_drive_id",
                "google_drive.root_folder_id",
            ],
        )

    def test_rejects_raw_oauth_application_credentials(self) -> None:
        value = desired()
        value["google_drive"]["oauth_client_id"] = "forbidden"  # type: ignore[index]
        with self.assertRaisesRegex(rclone_google_drive.BackupError, "forbidden"):
            rclone_google_drive.validate_desired(value)

    def test_password_command_is_an_absolute_space_separated_argument_list(self) -> None:
        encoded = rclone_google_drive.password_command("worker-linux")
        fields = next(csv.reader(io.StringIO(encoded), delimiter=" ", quotechar='"'))
        self.assertTrue(Path(fields[0]).is_absolute())
        self.assertTrue(Path(fields[1]).is_absolute())
        self.assertEqual(fields[2:], ["read", "--machine-id", "worker-linux"])

    def test_maps_personal_globals_only_into_the_rclone_child_environment(self) -> None:
        value = desired()
        client_id_name = "GOOGLE_PERSONAL_OAUTH_CLIENT_ID"
        client_secret_name = "GOOGLE_PERSONAL_OAUTH_CLIENT_SECRET"
        with patch.dict(
            os.environ,
            {
                rclone_google_drive.BINDINGS_CHILD_MARKER: "1",
                client_id_name: "synthetic-client-id",
                client_secret_name: "synthetic-client-secret",
            },
            clear=True,
        ):
            environment = rclone_google_drive.binding_environment(value)
        self.assertNotIn(client_id_name, environment)
        self.assertNotIn(client_secret_name, environment)
        self.assertNotIn(rclone_google_drive.BINDINGS_CHILD_MARKER, environment)
        self.assertEqual(
            environment["RCLONE_CONFIG_CTX9_CODEFOLDERSYNC_BACKUPS_CLIENT_ID"],
            "synthetic-client-id",
        )
        self.assertEqual(
            environment["RCLONE_CONFIG_CTX9_CODEFOLDERSYNC_BACKUPS_CLIENT_SECRET"],
            "synthetic-client-secret",
        )
        self.assertEqual(environment["RCLONE_DRIVE_CLIENT_ID"], "synthetic-client-id")
        self.assertEqual(environment["RCLONE_DRIVE_CLIENT_SECRET"], "synthetic-client-secret")
        self.assertEqual(environment["RCLONE_DRIVE_SCOPE"], "drive.file")

    def test_rejects_direct_execution_without_secret_bindings(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(rclone_google_drive.BackupError, "Secret Bindings"):
                rclone_google_drive.binding_environment(desired())


class ConfigurationTests(unittest.TestCase):
    def test_verifies_boundaries_from_private_process_output(self) -> None:
        rclone = Mock()
        rclone.desired = desired()
        rclone.run.side_effect = [
            Mock(stdout=""),
            Mock(
                stdout="""[ctx9_codefoldersync_backups]
type = drive
scope = drive.file
team_drive = shared-drive-id
root_folder_id = root-folder-id
token = synthetic-sensitive-token
"""
            ),
        ]
        report = rclone_google_drive.verify_remote(rclone, live=False)
        self.assertTrue(report["ready"])
        self.assertEqual(
            rclone.run.call_args_list,
            [
                call("config", "encryption", "check"),
                call("config", "show", "ctx9_codefoldersync_backups"),
            ],
        )
        self.assertNotIn("token", json.dumps(report))

    def test_rejects_persisted_application_credentials(self) -> None:
        rclone = Mock()
        rclone.desired = desired()
        rclone.run.side_effect = [
            Mock(stdout=""),
            Mock(
                stdout="""[ctx9_codefoldersync_backups]
type = drive
scope = drive.file
team_drive = shared-drive-id
root_folder_id = root-folder-id
client_id = forbidden
"""
            ),
        ]
        with self.assertRaisesRegex(rclone_google_drive.BackupError, "desired policy"):
            rclone_google_drive.verify_remote(rclone, live=False)

    def test_creates_only_the_exact_absent_remote(self) -> None:
        rclone = Mock()
        rclone.desired = desired()
        rclone.run.return_value.stdout = ""
        accepted = {"ready": True}
        with patch.object(rclone_google_drive, "verify_remote", return_value=accepted):
            report = rclone_google_drive.configure_remote(rclone)
        self.assertEqual(report, accepted)
        self.assertEqual(
            rclone.run.call_args_list,
            [
                call("config", "encryption", "check"),
                call("listremotes"),
            ],
        )
        rclone.run_oauth.assert_called_once_with(
            "config",
            "create",
            "ctx9_codefoldersync_backups",
            "drive",
            "scope",
            "drive.file",
            "team_drive",
            "shared-drive-id",
            "root_folder_id",
            "root-folder-id",
            "config_is_local",
            "true",
            "--no-output",
        )

    def test_encrypts_a_new_empty_config_before_oauth(self) -> None:
        rclone = Mock()
        rclone.desired = desired()
        empty = Mock(stdout="")
        success = Mock(stdout="")
        rclone.run.side_effect = [
            rclone_google_drive.BackupError("not encrypted"),
            empty,
            success,
            success,
            empty,
        ]
        with patch.object(rclone_google_drive, "verify_remote", return_value={"ready": True}):
            rclone_google_drive.configure_remote(rclone)
        self.assertEqual(
            rclone.run.call_args_list,
            [
                call("config", "encryption", "check"),
                call("listremotes"),
                call("config", "encryption", "set"),
                call("config", "encryption", "check"),
                call("listremotes"),
            ],
        )
        rclone.run_oauth.assert_called_once()

    def test_scrubs_application_credentials_from_oauth_output(self) -> None:
        rclone = object.__new__(rclone_google_drive.Rclone)
        rclone.executable = "/usr/bin/rclone"
        rclone.desired = desired()
        rclone.machine_id = "worker-linux"
        environment = {
            "RCLONE_CONFIG_CTX9_CODEFOLDERSYNC_BACKUPS_CLIENT_ID": "synthetic-client-id",
            "RCLONE_CONFIG_CTX9_CODEFOLDERSYNC_BACKUPS_CLIENT_SECRET": "synthetic-secret",
        }
        process = Mock()
        process.stdout = iter(
            ["default synthetic-client-id / synthetic-secret; open browser\n"]
        )
        process.wait.return_value = 0
        output = io.StringIO()
        with (
            patch.object(rclone, "_environment", return_value=environment),
            patch.object(rclone_google_drive.subprocess, "Popen", return_value=process) as popen,
            patch.object(rclone_google_drive.sys, "stdout", output),
        ):
            rclone.run_oauth("config", "create")
        self.assertNotIn("synthetic-client-id", output.getvalue())
        self.assertNotIn("synthetic-secret", output.getvalue())
        self.assertEqual(output.getvalue(), "default [REDACTED] / [REDACTED]; open browser\n")
        self.assertEqual(popen.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(popen.call_args.kwargs["stdout"], subprocess.PIPE)
        self.assertEqual(popen.call_args.kwargs["stderr"], subprocess.STDOUT)

    def test_authorize_token_keeps_credentials_out_of_arguments_and_output(self) -> None:
        rclone = object.__new__(rclone_google_drive.Rclone)
        rclone.executable = "/usr/bin/rclone"
        rclone.desired = desired()
        rclone.machine_id = "worker-mac"
        environment = {
            "RCLONE_DRIVE_CLIENT_ID": "synthetic-client-id",
            "RCLONE_DRIVE_CLIENT_SECRET": "synthetic-secret",
        }
        token = {
            "access_token": "access",
            "refresh_token": "refresh",
            "token_type": "Bearer",
            "expiry": "2030-01-01T00:00:00Z",
        }
        completed = Mock(returncode=0, stdout=f"safe progress\n{json.dumps(token)}\n")
        with (
            patch.object(rclone, "_environment", return_value=environment),
            patch.object(rclone_google_drive.subprocess, "run", return_value=completed) as run,
        ):
            result = rclone.authorize_token()
        self.assertEqual(json.loads(result), token)
        arguments = run.call_args.args[0]
        self.assertNotIn("synthetic-client-id", arguments)
        self.assertNotIn("synthetic-secret", arguments)
        self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(run.call_args.kwargs["stdout"], subprocess.PIPE)
        self.assertEqual(run.call_args.kwargs["stderr"], subprocess.STDOUT)

    def test_remote_configure_sends_token_only_over_ssh_stdin(self) -> None:
        rclone = Mock()
        rclone.desired = desired()
        rclone.machine_id = "worker-mac"
        token = json.dumps(
            {
                "access_token": "access",
                "refresh_token": "refresh",
                "token_type": "Bearer",
            }
        )
        rclone.authorize_token.return_value = token
        completed = Mock(returncode=0, stdout="sanitized remote output")
        with patch.object(
            rclone_google_drive.subprocess, "run", return_value=completed
        ) as run:
            report = rclone_google_drive.configure_remote_over_ssh(
                rclone,
                "worker-linux",
                "worker-linux",
                "/opt/ctx9/rclone_google_drive.py",
            )
        self.assertTrue(report["ready"])
        self.assertEqual(report["token_transfer"], "authenticated-ssh-stdin")
        self.assertEqual(run.call_args.kwargs["input"], token + "\n")
        self.assertNotIn(token, run.call_args.args[0])
        self.assertEqual(run.call_args.kwargs["stdout"], subprocess.PIPE)
        self.assertEqual(run.call_args.kwargs["stderr"], subprocess.STDOUT)

    def test_remote_configure_rejects_shell_metacharacters_in_target_path(self) -> None:
        rclone = Mock()
        rclone.desired = desired()
        rclone.machine_id = "worker-mac"
        with self.assertRaisesRegex(rclone_google_drive.BackupError, "absolute and safe"):
            rclone_google_drive.configure_remote_over_ssh(
                rclone,
                "worker-linux",
                "worker-linux",
                "/opt/controller.py;touch /tmp/unsafe",
            )
        rclone.authorize_token.assert_not_called()

    def test_configure_from_token_passes_token_only_through_stdin(self) -> None:
        rclone = Mock()
        rclone.desired = desired()
        token = json.dumps(
            {
                "access_token": "access",
                "refresh_token": "refresh",
                "token_type": "Bearer",
            }
        )
        with (
            patch.object(rclone_google_drive, "require_absent_encrypted_remote"),
            patch.object(rclone_google_drive, "verify_remote", return_value={"ready": True}),
        ):
            report = rclone_google_drive.configure_remote_from_token(rclone, token)
        self.assertTrue(report["ready"])
        self.assertEqual(rclone.run_oauth_input.call_args.args[0], token)
        self.assertNotIn(token, rclone.run_oauth_input.call_args.args[1:])

    def test_refuses_to_replace_an_existing_remote(self) -> None:
        rclone = Mock()
        rclone.desired = desired()
        rclone.run.return_value.stdout = "ctx9_codefoldersync_backups:\n"
        with self.assertRaisesRegex(rclone_google_drive.BackupError, "already exists"):
            rclone_google_drive.configure_remote(rclone)
        self.assertEqual(
            rclone.run.call_args_list,
            [call("config", "encryption", "check"), call("listremotes")],
        )
        rclone.run_oauth.assert_not_called()


class BundleTests(unittest.TestCase):
    def create_bundle(self, root: Path) -> None:
        artifact = root / "code.tar.zst.age"
        artifact.write_bytes(b"ciphertext fixture")
        witness = {
            "schema_version": 1,
            "snapshot_id": "snapshot-1",
            "machine_id": "primary-mac",
            "artifacts": [
                {
                    "name": artifact.name,
                    "size": artifact.stat().st_size,
                    "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                }
            ],
        }
        (root / "witness.json").write_text(json.dumps(witness) + "\n", encoding="utf-8")

    def test_validates_exact_flat_ciphertext_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.create_bundle(root)
            report = rclone_google_drive.validate_bundle(root, "snapshot-1", "primary-mac")
            self.assertEqual(report["artifact_count"], 1)
            self.assertEqual(report["file_count"], 2)

    def test_rejects_unbound_plaintext(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.create_bundle(root)
            (root / "manifest.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(rclone_google_drive.BackupError, "unbound"):
                rclone_google_drive.validate_bundle(root, "snapshot-1", "primary-mac")

    def test_rejects_tampered_ciphertext(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.create_bundle(root)
            (root / "code.tar.zst.age").write_bytes(b"changed")
            with self.assertRaisesRegex(rclone_google_drive.BackupError, "does not match"):
                rclone_google_drive.validate_bundle(root, "snapshot-1", "primary-mac")

    def test_remote_paths_reject_nested_components(self) -> None:
        with self.assertRaisesRegex(rclone_google_drive.BackupError, "unsafe"):
            rclone_google_drive.remote_path(desired(), "snapshots/other")


if __name__ == "__main__":
    unittest.main()
