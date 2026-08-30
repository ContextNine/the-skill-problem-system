from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from package_layout import ConfigurationError, expand_registered_path, validate_machines, validate_workspaces
from package_installer import InstallError, install, uninstall, verify


class PackageConfigurationTests(unittest.TestCase):
    def machines(self, home: str = "/opt/example-home", code: str = "~/workspace") -> dict[str, object]:
        return {
            "schema_version": 7,
            "primary_machine_id": "primary",
            "vault_git": {
                "owner_machine_id": None,
                "refresh_owner_machine_id": None,
                "remote": "origin",
                "branch": "master",
            },
            "machines": [
                {
                    "id": "primary",
                    "display_name": "Primary",
                    "enabled": True,
                    "role": "primary",
                    "platform": "linux",
                    "transport": "local",
                    "home": home,
                    "roots": {"code": code, "vault": None},
                    "vault": {"enabled": False, "checkout_mode": "none", "required": False},
                }
            ],
        }

    def test_registered_tilde_expands_against_selected_machine_home(self) -> None:
        self.assertEqual(expand_registered_path("~/workspace", "/opt/example-home"), "/opt/example-home/workspace")

    def test_workspace_targets_derive_from_code_root(self) -> None:
        machines = validate_machines(self.machines())
        workspaces = validate_workspaces(
            {"schema_version": 2, "entries": {"app": {"path": "clients/app"}}},
            machines,
        )
        self.assertEqual(workspaces["app"]["resolved_paths"]["primary"], "/opt/example-home/workspace/clients/app")

    def test_workspace_escape_and_absolute_paths_are_rejected(self) -> None:
        machines = validate_machines(self.machines())
        for value in ("../app", "/opt/app", "~/app"):
            with self.subTest(value=value), self.assertRaises(ConfigurationError):
                validate_workspaces({"schema_version": 2, "entries": {"app": {"path": value}}}, machines)

    def test_duplicate_targets_are_rejected(self) -> None:
        machines = validate_machines(self.machines())
        with self.assertRaises(ConfigurationError):
            validate_workspaces(
                {"schema_version": 2, "entries": {"one": {"path": "app"}, "two": {"path": "app"}}},
                machines,
            )

    def test_macos_and_linux_roots_resolve_from_the_registered_home(self) -> None:
        data = self.machines("/srv/example-macos/user", "~/" + "Code")
        data["machines"].append(
            {
                "id": "linux-worker",
                "display_name": "Linux worker",
                "enabled": True,
                "role": "worker",
                "platform": "linux",
                "transport": "ssh",
                "home": "/srv/example-linux/user",
                "roots": {"code": "~/" + "code", "vault": None},
                "vault": {"enabled": False, "checkout_mode": "none", "required": False},
            }
        )
        data["machines"][0]["roots"]["vault"] = "~/Vault"
        data["machines"][0]["platform"] = "macos"
        data["machines"][0]["vault"] = {
            "enabled": True,
            "checkout_mode": "primary-external-git",
            "required": True,
        }
        data["vault_git"]["owner_machine_id"] = "primary"
        data["vault_git"]["refresh_owner_machine_id"] = "primary"
        machines = validate_machines(data)
        self.assertEqual(machines["primary"]["roots"]["code"], "/srv/example-macos/user/Code")
        self.assertEqual(machines["primary"]["roots"]["vault"], "/srv/example-macos/user/Vault")
        self.assertEqual(machines["linux-worker"]["roots"]["code"], "/srv/example-linux/user/code")
        self.assertIsNone(machines["linux-worker"]["roots"]["vault"])

    def test_missing_code_root_is_rejected(self) -> None:
        data = self.machines()
        data["machines"][0]["roots"]["code"] = None
        with self.assertRaises(ConfigurationError):
            validate_machines(data)


class StandaloneInstallTests(unittest.TestCase):
    def test_install_verify_second_run_and_uninstall(self) -> None:
        package = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "user-home"
            home.mkdir()
            first = install(
                package,
                home,
                apply=True,
                global_instructions=False,
                claude_alias=False,
                discovery_aliases=False,
                machine_id="test-mac",
                code_root="~/Developer",
            )
            self.assertTrue(first["ok"])
            self.assertTrue(verify(home)["ok"])
            machines = json.loads(
                (home / ".config/ctx9/agents/fleet/machines.json").read_text(encoding="utf-8")
            )
            self.assertEqual(machines["primary_machine_id"], "test-mac")
            self.assertEqual(machines["machines"][0]["roots"]["code"], "~/Developer")
            second = install(
                package,
                home,
                apply=True,
                global_instructions=False,
                claude_alias=False,
                discovery_aliases=False,
                machine_id="test-mac",
                code_root="~/Developer",
            )
            self.assertTrue(second["ok"])
            self.assertIn("match", {action["status"] for action in second["actions"]})
            self.assertNotIn("backup", {action["status"] for action in second["actions"]})
            removed = uninstall(home, apply=True)
            self.assertTrue(removed["ok"])
            self.assertFalse((home / ".local/share/ctx9-agents").exists())

    def test_global_instruction_install_refuses_an_unmanaged_file(self) -> None:
        package = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "user-home"
            target = home / ".codex/AGENTS.md"
            target.parent.mkdir(parents=True)
            target.write_text("user-owned\n", encoding="utf-8")
            with self.assertRaisesRegex(InstallError, "unmanaged"):
                install(
                    package,
                    home,
                    apply=True,
                    global_instructions=True,
                    claude_alias=False,
                    discovery_aliases=False,
                )


if __name__ == "__main__":
    unittest.main()
