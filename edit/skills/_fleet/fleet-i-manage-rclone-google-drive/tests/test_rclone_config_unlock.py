from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import call, patch


SCRIPT = Path(__file__).parents[1] / "scripts/rclone_config_unlock.py"
SPEC = importlib.util.spec_from_file_location("rclone_config_unlock", SCRIPT)
assert SPEC and SPEC.loader
rclone_config_unlock = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rclone_config_unlock)


class ConfigUnlockTests(unittest.TestCase):
    def test_macos_lookup_is_fixed_to_machine_and_service(self) -> None:
        self.assertEqual(
            rclone_config_unlock.lookup_command("primary-mac", "darwin"),
            [
                "/usr/bin/security",
                "find-generic-password",
                "-a",
                "primary-mac",
                "-s",
                "ctx9-rclone-config-unlock",
                "-w",
            ],
        )

    def test_linux_lookup_is_fixed_to_provider_resource_and_machine(self) -> None:
        with patch.object(rclone_config_unlock.shutil, "which", return_value="/usr/bin/secret-tool"):
            command = rclone_config_unlock.lookup_command("worker-linux", "linux")
        self.assertEqual(command[-6:], ["ctx9-provider", "rclone-config-unlock", "ctx9-resource", "codefoldersync-backups", "ctx9-machine", "worker-linux"])

    def test_rejects_unsafe_machine_id(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsafe"):
            rclone_config_unlock.lookup_command("../primary-mac", "darwin")

    def test_macos_store_prompts_without_putting_value_in_argv(self) -> None:
        command = rclone_config_unlock.store_command("primary-mac", "darwin")
        self.assertEqual(command[-1], "-w")
        self.assertNotIn("generated-value", command)

    def test_linux_store_is_fixed_to_provider_resource_and_machine(self) -> None:
        with patch.object(rclone_config_unlock.shutil, "which", return_value="/usr/bin/secret-tool"):
            command = rclone_config_unlock.store_command("worker-linux", "linux")
        self.assertEqual(command[-6:], ["ctx9-provider", "rclone-config-unlock", "ctx9-resource", "codefoldersync-backups", "ctx9-machine", "worker-linux"])

    def test_generate_previews_without_writing(self) -> None:
        with (
            patch.object(rclone_config_unlock, "read_secret", return_value=None),
            patch.object(rclone_config_unlock, "store_secret") as store,
        ):
            report = rclone_config_unlock.generate("worker-linux", False, "linux")
        self.assertEqual(report["status"], "planned")
        store.assert_not_called()

    def test_generate_stores_once_and_verifies_round_trip(self) -> None:
        with (
            patch.object(rclone_config_unlock, "read_secret", side_effect=[None, "generated-value"]) as read,
            patch.object(rclone_config_unlock, "store_secret") as store,
            patch.object(rclone_config_unlock.secrets, "token_urlsafe", return_value="generated-value"),
        ):
            report = rclone_config_unlock.generate("worker-linux", True, "linux")
        self.assertEqual(report["status"], "created")
        self.assertTrue(report["verified"])
        store.assert_called_once_with("worker-linux", "generated-value", "linux")
        self.assertEqual(read.call_args_list, [call("worker-linux", "linux"), call("worker-linux", "linux")])

    def test_generate_never_replaces_an_existing_value(self) -> None:
        with (
            patch.object(rclone_config_unlock, "read_secret", return_value="existing-value"),
            patch.object(rclone_config_unlock, "store_secret") as store,
        ):
            report = rclone_config_unlock.generate("worker-linux", True, "linux")
        self.assertEqual(report["status"], "existing-unverified")
        store.assert_not_called()


if __name__ == "__main__":
    unittest.main()
