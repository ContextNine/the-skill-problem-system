from __future__ import annotations

import base64
import importlib.util
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("fleet_shell_access.py")
SPEC = importlib.util.spec_from_file_location("fleet_shell_access", SCRIPT)
assert SPEC and SPEC.loader
fleet = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fleet)


class FleetShellAccessTests(unittest.TestCase):
    def test_identity_path_accepts_reviewed_names_and_rejects_reserved_files(self) -> None:
        accepted = fleet.validate_identity_path(Path.home() / ".ssh/codex_fleet_ed25519")
        self.assertEqual(accepted.name, "codex_fleet_ed25519")

        with self.assertRaisesRegex(fleet.FleetShellError, "direct child"):
            fleet.validate_identity_path(Path.home() / ".ssh/authorized_keys")

    def test_authorize_preview_apply_verify_and_idempotence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            authorized_keys = root / ".ssh/authorized_keys"
            public_key = root / "source.pub"
            key_data = base64.b64encode(b"fleet-shell-public-key").decode()
            public_key.write_text(
                f"ssh-ed25519 {key_data} ctx9-fleet-shell:source\n",
                encoding="utf-8",
            )
            _, fingerprint = fleet.parse_public_key(public_key.read_text(encoding="utf-8"))

            preview = fleet.authorize(
                "source",
                authorized_keys,
                public_key,
                fingerprint,
                mode="dry-run",
            )
            self.assertEqual(preview["action"], "would-add-managed-public-key")
            self.assertFalse(authorized_keys.exists())

            applied = fleet.authorize(
                "source",
                authorized_keys,
                public_key,
                fingerprint,
                mode="apply",
            )
            self.assertTrue(applied["ready"])
            self.assertEqual(authorized_keys.stat().st_mode & 0o777, 0o600)

            verified = fleet.authorize(
                "source",
                authorized_keys,
                public_key,
                fingerprint,
                mode="verify",
            )
            self.assertTrue(verified["ready"])
            self.assertEqual(verified["action"], "none")

    def test_authorize_refuses_conflicting_managed_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            authorized_keys = root / "authorized_keys"
            first = base64.b64encode(b"first-key").decode()
            second = base64.b64encode(b"second-key").decode()
            authorized_keys.write_text(
                "# BEGIN ctx9 fleet shell: source\n"
                f"ssh-ed25519 {first} ctx9-fleet-shell:source\n"
                "# END ctx9 fleet shell: source\n",
                encoding="utf-8",
            )
            public_key = root / "source.pub"
            public_key.write_text(f"ssh-ed25519 {second}\n", encoding="utf-8")
            _, fingerprint = fleet.parse_public_key(public_key.read_text(encoding="utf-8"))

            with self.assertRaisesRegex(fleet.FleetShellError, "conflicting"):
                fleet.authorize(
                    "source",
                    authorized_keys,
                    public_key,
                    fingerprint,
                    mode="apply",
                )


if __name__ == "__main__":
    unittest.main()
