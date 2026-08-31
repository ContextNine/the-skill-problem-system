from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import stat
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("codefoldersync_backup_age.py")
SPEC = importlib.util.spec_from_file_location("codefoldersync_backup_age", SCRIPT)
assert SPEC and SPEC.loader
backup_age = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(backup_age)


@unittest.skipUnless(shutil.which("age") and shutil.which("age-keygen"), "age is required")
class CodeFolderSyncBackupAgeTests(unittest.TestCase):
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
            home = root / "mattbook"
            home.mkdir(mode=0o700)
            path = backup_age.identity_path(home)

            preview = backup_age.preview_generation("mattbook", path)
            self.assertEqual(preview["status"], "ready-to-generate")
            report = backup_age.generate_identity("mattbook", path)
            self.assertEqual(report["status"], "generated-unverified")
            self.assertFalse(report["accepted"])
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)

            with self.assertRaisesRegex(backup_age.LifecycleError, "never overwrite"):
                backup_age.generate_identity("mattbook", path)
            inspected = backup_age.inspect_identity("mattbook", path)
            self.assertEqual(inspected["status"], "existing-unverified")
            self.assertFalse(inspected["accepted"])

    def test_same_fixture_is_decrypted_by_distinct_recovery_identities(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.private_root(temporary, "run")
            matt_path, matt_generated = self.identity(root, "mattbook")
            woot_path, woot_generated = self.identity(root, "wootbook")
            ciphertext = root / "shared-fixture.age"
            fixture = backup_age.create_fixture(
                "acceptance-001",
                [str(matt_generated["recipient"]), str(woot_generated["recipient"])],
                ciphertext,
            )
            manifest = self.write_manifest(root, fixture)

            matt = backup_age.verify_fixture("mattbook", matt_path, ciphertext, manifest)
            woot = backup_age.verify_fixture("wootbook", woot_path, ciphertext, manifest)
            self.assertTrue(matt["accepted"])
            self.assertTrue(woot["accepted"])
            self.assertNotEqual(matt["recipient"], woot["recipient"])
            self.assertEqual(matt["fixture_ciphertext_sha256"], woot["fixture_ciphertext_sha256"])
            self.assertEqual(matt["fixture_plaintext_sha256"], woot["fixture_plaintext_sha256"])

    def test_acceptance_updates_only_sanitized_machine_records(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.private_root(temporary, "run")
            matt_path, matt_generated = self.identity(root, "mattbook")
            woot_path, woot_generated = self.identity(root, "wootbook")
            ciphertext = root / "shared-fixture.age"
            fixture = backup_age.create_fixture(
                "acceptance-002",
                [str(matt_generated["recipient"]), str(woot_generated["recipient"])],
                ciphertext,
            )
            manifest = self.write_manifest(root, fixture)
            reports = [
                backup_age.verify_fixture("mattbook", matt_path, ciphertext, manifest),
                backup_age.verify_fixture("wootbook", woot_path, ciphertext, manifest),
            ]
            state_path = root / "machine-secrets.lock.json"
            state_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "machines": {
                            "mattbook": {"platform": "macos", "unrelated": {"ready": True}},
                            "wootbook": {"platform": "linux"},
                        },
                    }
                ),
                encoding="utf-8",
            )

            accepted = backup_age.accepted_state(reports, state_path)
            self.assertTrue(accepted["machines"]["mattbook"]["unrelated"]["ready"])
            for machine_id in backup_age.RECOVERY_MACHINES:
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
        matt = {
            **base,
            "machine_id": "mattbook",
            "recipient": recipient_a,
            "recipient_sha256": backup_age.recipient_fingerprint(recipient_a),
        }
        woot = {
            **base,
            "machine_id": "wootbook",
            "recipient": recipient_b,
            "recipient_sha256": backup_age.recipient_fingerprint(recipient_b),
        }
        backup_age.validate_acceptance_reports([matt, woot])

        with self.assertRaisesRegex(backup_age.LifecycleError, "same fixture"):
            backup_age.validate_acceptance_reports([matt, {**woot, "fixture_id": "acceptance-004"}])
        duplicate = {
            **woot,
            "recipient": recipient_a,
            "recipient_sha256": backup_age.recipient_fingerprint(recipient_a),
        }
        with self.assertRaisesRegex(backup_age.LifecycleError, "distinct"):
            backup_age.validate_acceptance_reports([matt, duplicate])

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
