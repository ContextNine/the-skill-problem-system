from __future__ import annotations

import base64
import hashlib
import hmac
import importlib.util
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("trust_known_host_alias.py")
SPEC = importlib.util.spec_from_file_location("trust_known_host_alias", SCRIPT)
assert SPEC and SPEC.loader
trust = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trust)


def hashed_host(host: str) -> str:
    salt = b"stable-test-salt"
    digest = hmac.new(salt, host.encode(), hashlib.sha1).digest()
    return "|1|{}|{}".format(
        base64.b64encode(salt).decode(),
        base64.b64encode(digest).decode(),
    )


class TrustKnownHostAliasTests(unittest.TestCase):
    def test_dry_run_apply_verify_and_idempotence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            known_hosts = Path(temporary) / ".ssh/known_hosts"
            known_hosts.parent.mkdir()
            key_data = base64.b64encode(b"trusted-ed25519-key").decode()
            expected = trust.fingerprint(key_data)
            known_hosts.write_text(
                f"{hashed_host('10.13.13.2')} ssh-ed25519 {key_data}\n",
                encoding="utf-8",
            )

            preview = trust.reconcile(
                known_hosts,
                source_host="10.13.13.2",
                target_host="primary.example.ts.net",
                expected_fingerprint=expected,
                key_type="ssh-ed25519",
                mode="dry-run",
            )
            self.assertEqual(preview["action"], "would-add-exact-trusted-alias")
            self.assertNotIn("primary.example.ts.net", known_hosts.read_text(encoding="utf-8"))

            applied = trust.reconcile(
                known_hosts,
                source_host="10.13.13.2",
                target_host="primary.example.ts.net",
                expected_fingerprint=expected,
                key_type="ssh-ed25519",
                mode="apply",
            )
            self.assertEqual(applied["action"], "added-exact-trusted-alias")
            self.assertTrue(applied["ready"])
            self.assertEqual(known_hosts.stat().st_mode & 0o777, 0o600)

            verified = trust.reconcile(
                known_hosts,
                source_host="10.13.13.2",
                target_host="primary.example.ts.net",
                expected_fingerprint=expected,
                key_type="ssh-ed25519",
                mode="verify",
            )
            self.assertEqual(verified["action"], "none")
            self.assertTrue(verified["ready"])

    def test_refuses_conflicting_target_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            known_hosts = Path(temporary) / "known_hosts"
            trusted = base64.b64encode(b"trusted-key").decode()
            conflicting = base64.b64encode(b"conflicting-key").decode()
            known_hosts.write_text(
                "\n".join(
                    [
                        f"10.13.13.2 ssh-ed25519 {trusted}",
                        f"primary.example.ts.net ssh-ed25519 {conflicting}",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(trust.TrustError, "conflicting"):
                trust.reconcile(
                    known_hosts,
                    source_host="10.13.13.2",
                    target_host="primary.example.ts.net",
                    expected_fingerprint=trust.fingerprint(trusted),
                    key_type="ssh-ed25519",
                    mode="apply",
                )


if __name__ == "__main__":
    unittest.main()
