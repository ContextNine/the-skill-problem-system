from __future__ import annotations

import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from package_layout import ConfigurationError, expand_registered_path, validate_machines, validate_workspaces
from package_installer import WORKSPACE_SYNC_HELPERS, InstallError, install, is_private_source, uninstall, verify
from fleet_templates import FleetTemplateError, render_bundle


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


class FleetTemplateTests(unittest.TestCase):
    def test_skill_and_supporting_files_render_deterministically_and_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)
            templates = bundle / "fleet-templates"
            templates.mkdir()
            (bundle / "SKILL.md").write_text(
                "---\nname: code-example\ndescription: Test.\n---\n\n# Code · Example\n",
                encoding="utf-8",
            )
            (bundle / "facts.md").write_text("Base.\n", encoding="utf-8")
            (templates / "machine.md").write_text("Machine {machine_id}.\n", encoding="utf-8")
            config = templates / "render.json"
            config.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "outputs": [
                            {
                                "target": "facts.md",
                                "base": "facts.md",
                                "format": "markdown",
                                "fragments": [
                                    {
                                        "id": "machine:{machine_id}",
                                        "path": "fleet-templates/machine.md",
                                        "when": {"platform": "linux"},
                                    }
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            first = render_bundle(bundle, config, {"machine_id": "worker", "platform": "linux"})
            second = render_bundle(bundle, config, {"machine_id": "worker", "platform": "linux"})
            self.assertEqual(first, second)
            self.assertEqual(first[0].content, "Base.\n\n***\n\nMachine worker.\n")

            (templates / "machine.md").write_text("Machine {unknown}.\n", encoding="utf-8")
            with self.assertRaisesRegex(FleetTemplateError, "unknown variable"):
                render_bundle(bundle, config, {"machine_id": "worker", "platform": "linux"})


class StandaloneInstallTests(unittest.TestCase):
    def test_install_verify_second_run_and_uninstall(self) -> None:
        package = Path(__file__).resolve().parents[2]
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
            installed_manifest = home / ".agents/state/installed.json"
            stale = json.loads(installed_manifest.read_text(encoding="utf-8"))
            stale["package_version"] = "0.0.0"
            installed_manifest.write_text(json.dumps(stale), encoding="utf-8")
            self.assertFalse(verify(home)["ok"])
            machines = json.loads(
                (home / ".agents/settings/fleet/machines.json").read_text(encoding="utf-8")
            )
            self.assertEqual(machines["primary_machine_id"], "test-mac")
            self.assertEqual(machines["machines"][0]["roots"]["code"], "~/Developer")
            self.assertEqual((home / ".agents/internal/skills").exists(), not is_private_source(package))
            for helper in WORKSPACE_SYNC_HELPERS:
                self.assertTrue((home / ".agents/internal/src" / helper).is_file())
            launcher = (home / ".local/bin/fleet").read_text(encoding="utf-8")
            command_root = package.parents[1] if is_private_source(package) else package
            self.assertIn(f"--root {json.dumps(str(command_root.resolve()))}", launcher)
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
            self.assertTrue(verify(home)["ok"])
            self.assertIn("match", {action["status"] for action in second["actions"]})
            self.assertNotIn("backup", {action["status"] for action in second["actions"]})
            removed = uninstall(home, apply=True)
            self.assertTrue(removed["ok"])
            self.assertFalse((home / ".agents/internal").exists())

    def test_global_instruction_install_refuses_an_unmanaged_file(self) -> None:
        package = Path(__file__).resolve().parents[2]
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

    def test_existing_fleet_worker_keeps_the_primary_owned_registry(self) -> None:
        package = Path(__file__).resolve().parents[2]
        source_registry = json.loads(
            (package / "edit/settings/fleet/machines.json").read_text(encoding="utf-8")
        )
        worker_id = next(
            (
                machine["id"]
                for machine in source_registry["machines"]
                if machine.get("role") == "worker" and machine.get("enabled")
            ),
            None,
        )
        if worker_id is None:
            self.skipTest("public starter settings do not include a worker")
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "worker-home"
            home.mkdir()
            report = install(
                package,
                home,
                apply=True,
                global_instructions=False,
                claude_alias=False,
                discovery_aliases=False,
                machine_id=worker_id,
            )
            self.assertTrue(report["ready"])
            installed_registry = json.loads(
                (home / ".agents/settings/fleet/machines.json").read_text(encoding="utf-8")
            )
            self.assertEqual(installed_registry, source_registry)

    def test_command_root_overrides_a_temporary_private_source(self) -> None:
        package = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "migration-source"
            registered_root = root / "Vault"
            home = root / "worker-home"
            home.mkdir()
            shutil.copytree(package, source, symlinks=True)
            report = install(
                source,
                home,
                apply=True,
                global_instructions=False,
                claude_alias=False,
                discovery_aliases=False,
                command_root=registered_root,
            )
            self.assertTrue(report["ready"])
            launcher = (home / ".local/bin/fleet").read_text(encoding="utf-8")
            self.assertIn(f"--root {json.dumps(str(registered_root.resolve()))}", launcher)


if __name__ == "__main__":
    unittest.main()
