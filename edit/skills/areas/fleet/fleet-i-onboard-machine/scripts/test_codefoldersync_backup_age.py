from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).with_name("codefoldersync_backup_age.py")
SPEC = importlib.util.spec_from_file_location("codefoldersync_backup_age", SCRIPT)
assert SPEC and SPEC.loader
backup_age = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(backup_age)


@unittest.skipUnless(shutil.which("age") and shutil.which("age-keygen"), "age is required")
class CodeFolderSyncBackupAgeTests(unittest.TestCase):
    def setUp(self) -> None:
        configured = patch.object(backup_age, "recovery_machines", return_value=frozenset({"primary-mac", "worker-linux"}))
        configured.start()
        self.addCleanup(configured.stop)

    def test_recovery_machine_selection_requires_configured_distinct_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "backup-recovery.json"
            path.write_text(json.dumps({"schema_version": 1, "recovery_machines": ["primary-mac", "worker-linux"]}), encoding="utf-8")
            self.assertEqual(backup_age.load_recovery_machines(path), frozenset({"primary-mac", "worker-linux"}))
            path.write_text(json.dumps({"schema_version": 1, "recovery_machines": []}), encoding="utf-8")
            with self.assertRaises(backup_age.LifecycleError):
                backup_age.load_recovery_machines(path)

    def private_root(self, temporary: str, name: str) -> Path:
        root = Path(temporary) / name
        root.mkdir(mode=0o700)
        root.chmod(0o700)
        return root

    def identity(self, root: Path, machine_id: str) -> tuple[Path, dict[str, object]]:
        home = root / machine_id
        home.mkdir(mode=0o700)
        path = backup_age.identity_path(home)
        report = backup_age.generate_identity(machine_id, path)
        return path, report

    def write_manifest(self, root: Path, value: dict[str, object]) -> Path:
        path = root / "fixture.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        path.chmod(0o600)
        return path

    def test_generation_is_target_local_and_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.private_root(temporary, "run")
            home = root / "primary-mac"
            home.mkdir(mode=0o700)
            path = backup_age.identity_path(home)

            preview = backup_age.preview_generation("primary-mac", path)
            self.assertEqual(preview["status"], "ready-to-generate")
            report = backup_age.generate_identity("primary-mac", path)
            self.assertEqual(report["status"], "generated-unverified")
            self.assertFalse(report["accepted"])
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)

            with self.assertRaisesRegex(backup_age.LifecycleError, "never overwrite"):
                backup_age.generate_identity("primary-mac", path)
            inspected = backup_age.inspect_identity("primary-mac", path)
            self.assertEqual(inspected["status"], "existing-unverified")
            self.assertFalse(inspected["accepted"])

    def test_same_fixture_is_decrypted_by_distinct_recovery_identities(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.private_root(temporary, "run")
            primary_path, primary_generated = self.identity(root, "primary-mac")
            worker_path, worker_generated = self.identity(root, "worker-linux")
            ciphertext = root / "shared-fixture.age"
            fixture = backup_age.create_fixture(
                "acceptance-001",
                [str(primary_generated["recipient"]), str(worker_generated["recipient"])],
                ciphertext,
            )
            manifest = self.write_manifest(root, fixture)

            primary = backup_age.verify_fixture("primary-mac", primary_path, ciphertext, manifest)
            worker = backup_age.verify_fixture("worker-linux", worker_path, ciphertext, manifest)
            self.assertTrue(primary["accepted"])
            self.assertTrue(worker["accepted"])
            self.assertNotEqual(primary["recipient"], worker["recipient"])
            self.assertEqual(primary["fixture_ciphertext_sha256"], worker["fixture_ciphertext_sha256"])
            self.assertEqual(primary["fixture_plaintext_sha256"], worker["fixture_plaintext_sha256"])

    def test_acceptance_updates_only_sanitized_machine_records(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.private_root(temporary, "run")
            primary_path, primary_generated = self.identity(root, "primary-mac")
            worker_path, worker_generated = self.identity(root, "worker-linux")
            ciphertext = root / "shared-fixture.age"
            fixture = backup_age.create_fixture(
                "acceptance-002",
                [str(primary_generated["recipient"]), str(worker_generated["recipient"])],
                ciphertext,
            )
            manifest = self.write_manifest(root, fixture)
            reports = [
                backup_age.verify_fixture("primary-mac", primary_path, ciphertext, manifest),
                backup_age.verify_fixture("worker-linux", worker_path, ciphertext, manifest),
            ]
            state_path = root / "machine-secrets.lock.json"
            state_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "machines": {
                            "primary-mac": {"platform": "macos", "unrelated": {"ready": True}},
                            "worker-linux": {"platform": "linux"},
                        },
                    }
                ),
                encoding="utf-8",
            )

            accepted = backup_age.accepted_state(reports, state_path)
            self.assertTrue(accepted["machines"]["primary-mac"]["unrelated"]["ready"])
            for machine_id in backup_age.recovery_machines():
                record = accepted["machines"][machine_id][backup_age.CREDENTIAL_ID]
                self.assertTrue(record["accepted"])
                self.assertNotIn("identity", record)
                self.assertEqual(record["custody_path"], "~/.config/ctx9/codefoldersync/backup-recovery.agekey")

    def test_acceptance_rejects_different_fixture_or_duplicate_recipient(self) -> None:
        recipient_a = "age1" + "a" * 58
        recipient_b = "age1" + "c" * 58
        base = {
            "schema_version": 1,
            "credential_id": backup_age.CREDENTIAL_ID,
            "custody": "target-local-age-file",
            "custody_path": backup_age.custody_path(),
            "identity_mode": "0600",
            "fixture_id": "acceptance-003",
            "fixture_ciphertext_sha256": "1" * 64,
            "fixture_plaintext_sha256": "2" * 64,
            "verified_at": "2026-08-30T00:00:00Z",
            "accepted": True,
        }
        primary = {
            **base,
            "machine_id": "primary-mac",
            "recipient": recipient_a,
            "recipient_sha256": backup_age.recipient_fingerprint(recipient_a),
        }
        worker = {
            **base,
            "machine_id": "worker-linux",
            "recipient": recipient_b,
            "recipient_sha256": backup_age.recipient_fingerprint(recipient_b),
        }
        backup_age.validate_acceptance_reports([primary, worker])

        with self.assertRaisesRegex(backup_age.LifecycleError, "same fixture"):
            backup_age.validate_acceptance_reports([primary, {**worker, "fixture_id": "acceptance-004"}])
        duplicate = {
            **worker,
            "recipient": recipient_a,
            "recipient_sha256": backup_age.recipient_fingerprint(recipient_a),
        }
        with self.assertRaisesRegex(backup_age.LifecycleError, "distinct"):
            backup_age.validate_acceptance_reports([primary, duplicate])

    def test_report_writer_is_private_and_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.private_root(temporary, "run")
            report = root / "generation.json"
            backup_age.write_new_json(report, {"recipient": "public"})
            self.assertEqual(stat.S_IMODE(report.stat().st_mode), 0o600)
            with self.assertRaisesRegex(backup_age.LifecycleError, "already exists"):
                backup_age.write_new_json(report, {"recipient": "replacement"})
            self.assertEqual(json.loads(report.read_text(encoding="utf-8")), {"recipient": "public"})


if __name__ == "__main__":
    unittest.main()
