#!/usr/bin/env python3
"""Focused tests for macOS gh Keychain repair."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


SCRIPT = Path(__file__).with_name("macos_gh_keychain.py")
SPEC = importlib.util.spec_from_file_location("macos_gh_keychain", SCRIPT)
assert SPEC and SPEC.loader
repair = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = repair
SPEC.loader.exec_module(repair)


class MacOSGhKeychainTests(unittest.TestCase):
    def test_plaintext_tokens_are_removed_without_changing_metadata(self) -> None:
        original = (
            b"github.com:\n"
            b"    git_protocol: ssh\n"
            b"    users:\n"
            b"        MDerman:\n"
            b"            oauth_token: secret-one\n"
            b"    user: MDerman\n"
            b"    oauth_token: secret-two\n"
        )
        self.assertEqual(
            repair.without_plaintext_tokens(original),
            b"github.com:\n"
            b"    git_protocol: ssh\n"
            b"    users:\n"
            b"        MDerman:\n"
            b"    user: MDerman\n",
        )


if __name__ == "__main__":
    unittest.main()
