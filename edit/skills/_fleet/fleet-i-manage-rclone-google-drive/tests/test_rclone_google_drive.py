from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).parents[1] / "scripts/rclone_google_drive.py"
SPEC = importlib.util.spec_from_file_location("rclone_google_drive", SCRIPT)
assert SPEC and SPEC.loader
rclone_google_drive = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rclone_google_drive)


def desired(enabled: bool = True) -> dict[str, object]:
    return {
        "schema_version": 1,
        "enabled": enabled,
        "remote_name": "ctx9_codefoldersync_backups",
        "allowed_machines": ["primary-mac", "worker-linux", "worker-mac"],
        "google_drive": {
            "oauth_client_id": "public-client-id",
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
        value["google_drive"]["oauth_client_id"] = None  # type: ignore[index]
        value["google_drive"]["shared_drive_id"] = None  # type: ignore[index]
        value["google_drive"]["root_folder_id"] = None  # type: ignore[index]
        self.assertEqual(
            rclone_google_drive.desired_missing(rclone_google_drive.validate_desired(value)),
            [
                "enabled",
                "allowed_machines",
                "google_drive.oauth_client_id",
                "google_drive.shared_drive_id",
                "google_drive.root_folder_id",
            ],
        )

    def test_password_command_is_an_absolute_space_separated_argument_list(self) -> None:
        encoded = rclone_google_drive.password_command("worker-linux")
        fields = next(csv.reader(io.StringIO(encoded), delimiter=" ", quotechar='"'))
        self.assertTrue(Path(fields[0]).is_absolute())
        self.assertTrue(Path(fields[1]).is_absolute())
        self.assertEqual(fields[2], "worker-linux")


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
