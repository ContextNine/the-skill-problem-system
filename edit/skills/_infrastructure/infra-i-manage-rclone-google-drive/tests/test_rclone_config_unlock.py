from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).parents[1] / "scripts/rclone_config_unlock.py"
SPEC = importlib.util.spec_from_file_location("rclone_config_unlock", SCRIPT)
assert SPEC and SPEC.loader
rclone_config_unlock = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rclone_config_unlock)


class ConfigUnlockTests(unittest.TestCase):
    def test_macos_lookup_is_fixed_to_machine_and_service(self) -> None:
        self.assertEqual(
            rclone_config_unlock.command_for("mattbook", "darwin"),
            [
                "/usr/bin/security",
                "find-generic-password",
                "-a",
                "mattbook",
                "-s",
                "ctx9-rclone-config-unlock",
                "-w",
            ],
        )

    def test_linux_lookup_is_fixed_to_provider_resource_and_machine(self) -> None:
        with patch.object(rclone_config_unlock.shutil, "which", return_value="/usr/bin/secret-tool"):
            command = rclone_config_unlock.command_for("wootbook", "linux")
        self.assertEqual(command[-6:], ["ctx9-provider", "rclone-config-unlock", "ctx9-resource", "codefoldersync-backups", "ctx9-machine", "wootbook"])

    def test_rejects_unsafe_machine_id(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsafe"):
            rclone_config_unlock.command_for("../mattbook", "darwin")


if __name__ == "__main__":
    unittest.main()

