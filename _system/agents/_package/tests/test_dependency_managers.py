from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import dependency_worker
import fleet_update_worker


class RcloneManagerTests(unittest.TestCase):
    def test_default_registry_uses_signed_rclone_updates_on_linux(self) -> None:
        package = Path(__file__).resolve().parents[1]
        manifest = json.loads((package / "defaults/dependencies.json").read_text(encoding="utf-8"))

        dependency_worker.validate_manifest(manifest)
        rclone = next(item for item in manifest["dependencies"] if item["id"] == "rclone")

        self.assertEqual(
            rclone["contract"]["recipes"]["linux"],
            {"manager": "rclone-selfupdate", "package": "rclone"},
        )

    def test_fleet_update_uses_rclone_signed_debian_package_channel(self) -> None:
        with patch.object(fleet_update_worker.shutil, "which", return_value="/usr/bin/rclone"):
            self.assertEqual(
                fleet_update_worker.package_update_command("rclone-selfupdate", "rclone"),
                [
                    "sudo",
                    "-n",
                    "/usr/bin/rclone",
                    "selfupdate",
                    "--stable",
                    "--package",
                    "deb",
                ],
            )


if __name__ == "__main__":
    unittest.main()
