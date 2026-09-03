from __future__ import annotations

import importlib.util
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).with_name("enroll_sops_key.py")
SPEC = importlib.util.spec_from_file_location("enroll_sops_key", SCRIPT)
assert SPEC and SPEC.loader
enroll = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(enroll)


class EnrollSopsKeyTests(unittest.TestCase):
    def key_file(self, directory: str, mode: int = 0o600) -> Path:
        path = Path(directory) / "key.txt"
        path.write_text("test identity\n", encoding="utf-8")
        path.chmod(mode)
        return path

    def test_digest_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.key_file(temporary)
            self.assertEqual(enroll.digest(source), enroll.digest(source))

    def test_source_rejects_open_permissions(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.key_file(temporary, 0o644)
            with self.assertRaises(PermissionError):
                enroll.validate_source(source)

    def test_source_rejects_open_directory_permissions(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.key_file(temporary)
            Path(temporary).chmod(0o755)
            with self.assertRaises(PermissionError):
                enroll.validate_source(source)

    def test_repo_path_must_be_absolute(self):
        with self.assertRaisesRegex(ValueError, "absolute"):
            enroll.validate_repo_path("relative/repo")

    def test_source_recipients_supports_rotation_bundle(self):
        completed = enroll.subprocess.CompletedProcess(
            ["age-keygen"],
            0,
            stdout="age1old\nage1new\n",
            stderr="",
        )
        with patch.object(enroll, "run", return_value=completed):
            self.assertEqual(
                enroll.source_recipients(Path("key.txt")),
                ("age1old", "age1new"),
            )

    def test_source_recipients_rejects_duplicates(self):
        completed = enroll.subprocess.CompletedProcess(
            ["age-keygen"],
            0,
            stdout="age1same\nage1same\n",
            stderr="",
        )
        with patch.object(enroll, "run", return_value=completed):
            with self.assertRaisesRegex(RuntimeError, "duplicate"):
                enroll.source_recipients(Path("key.txt"))


if __name__ == "__main__":
    unittest.main()
