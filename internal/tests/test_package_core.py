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
from fleet_templates import FleetTemplateError, render_file, render_markdown_tree


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
                    "template_variants": ["linux", "workerlinux"],
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
            {"schema_version": 3, "entries": {"app": {"path": "clients/app"}}},
            machines,
        )
        self.assertEqual(workspaces["app"]["resolved_paths"]["primary"], "/opt/example-home/workspace/clients/app")

    def test_workspace_escape_and_absolute_paths_are_rejected(self) -> None:
        machines = validate_machines(self.machines())
        for value in ("../app", "/opt/app", "~/app"):
            with self.subTest(value=value), self.assertRaises(ConfigurationError):
                validate_workspaces({"schema_version": 3, "entries": {"app": {"path": value}}}, machines)

    def test_duplicate_targets_are_rejected(self) -> None:
        machines = validate_machines(self.machines())
        with self.assertRaises(ConfigurationError):
            validate_workspaces(
                {"schema_version": 3, "entries": {"one": {"path": "app"}, "two": {"path": "app"}}},
                machines,
            )

    def test_workspace_development_targets_are_repository_specific_and_non_secret(self) -> None:
        machines = validate_machines(self.machines())
        registry = {
            "schema_version": 3,
            "entries": {
                "impression": {
                    "path": "impression",
                    "development": {
                        "environment": "local",
                        "k3s_context": "example-cluster",
                        "namespace": "impression-local",
                        "postgres_service": "postgres-pooler.postgres.svc.cluster.local",
                        "postgres_direct_service": "postgres-rw.postgres.svc.cluster.local",
                        "redis_service": "redis.redis.svc.cluster.local",
                    },
                },
                "rnr": {
                    "path": "rnr",
                    "development": {
                        "environment": "local",
                        "k3s_context": "example-cluster",
                        "namespace": "rnr-local",
                        "postgres_service": "postgres-pooler.postgres.svc.cluster.local",
                        "postgres_direct_service": "postgres-rw.postgres.svc.cluster.local",
                        "redis_service": None,
                    },
                },
                "without-development": {"path": "without-development"},
            },
        }
        workspaces = validate_workspaces(registry, machines)
        self.assertEqual(workspaces["impression"]["development"]["namespace"], "impression-local")
        self.assertIsNone(workspaces["rnr"]["development"]["redis_service"])
        self.assertNotIn("development", workspaces["without-development"])

    def test_workspace_development_targets_reject_credentials_and_managed_namespaces(self) -> None:
        machines = validate_machines(self.machines())
        valid = {
            "environment": "local",
            "k3s_context": "example-cluster",
            "namespace": "app-local",
            "postgres_service": "postgres-pooler.postgres.svc.cluster.local",
            "postgres_direct_service": "postgres-rw.postgres.svc.cluster.local",
            "redis_service": None,
        }
        invalid_targets = [
            {**valid, "environment": "prod"},
            {**valid, "namespace": "app-prod"},
            {**valid, "postgres_service": "postgres://user:password@example.test/db"},
            {**valid, "redis_service": "redis://secret@example.test"},
        ]
        for target in invalid_targets:
            with self.subTest(target=target), self.assertRaises(ConfigurationError):
                validate_workspaces(
                    {"schema_version": 3, "entries": {"app": {"path": "app", "development": target}}},
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
                "template_variants": ["linux", "workerlinux"],
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
            templates = bundle / "templates"
            templates.mkdir()
            (bundle / "SKILL.md").write_text(
                "---\nname: code-example\ndescription: Test.\n---\n\n"
                "# Example\n\n{{ fleet.machine.display_name }}\n"
                "{% include \"templates/runtime.md\" %}\n",
                encoding="utf-8",
            )
            reference = bundle / "references/facts.md"
            reference.parent.mkdir()
            reference.write_text(
                "{% include \"templates/runtime.md\" %}\n"
                "\\{{ fleet.machine.display_name }} and \\{% include \"templates/runtime.md\" %}\n"
                "{{first_name}}\n",
                encoding="utf-8",
            )
            (templates / "runtime.md").write_text("Common runtime.\n", encoding="utf-8")
            (templates / "runtime.linux.md").write_text("Linux runtime.\n", encoding="utf-8")
            (templates / "runtime.workerlinux.md").write_text("Worker runtime.\n", encoding="utf-8")
            context = {"fleet": {"machine": {"display_name": "Wootbook"}}}
            variants = ["linux", "workerlinux"]
            first = render_file(bundle, bundle / "SKILL.md", context, variants)
            self.assertEqual(first, render_file(bundle, bundle / "SKILL.md", context, variants))
            self.assertIn("Wootbook\nWorker runtime.", first)
            self.assertEqual(
                render_file(bundle, reference, context, ["linux"]),
                'Linux runtime.\n\n{{ fleet.machine.display_name }} and {% include "templates/runtime.md" %}\n{{first_name}}\n',
            )
            render_markdown_tree(bundle, context, variants)
            self.assertIn("Worker runtime.\n\n{{ fleet.machine.display_name }}", reference.read_text())
            self.assertEqual((templates / "runtime.workerlinux.md").read_text(), "Worker runtime.\n")

            (templates / "runtime.workerlinux.md").unlink()
            (templates / "runtime.linux.md").unlink()
            (templates / "runtime.md").unlink()
            reference.write_text('{% include "templates/runtime.md" %}\n', encoding="utf-8")
            with self.assertRaisesRegex(FleetTemplateError, "missing include"):
                render_file(bundle, reference, context, variants)

            reference.write_text('{% include "templates/../escape.md" %}\n', encoding="utf-8")
            with self.assertRaisesRegex(FleetTemplateError, "invalid include|escapes"):
                render_file(bundle, reference, context, variants)


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
            self.assertNotIn("fleet.managed", launcher)
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

    def test_global_instruction_install_replaces_existing_file_without_a_marker(self) -> None:
        package = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "user-home"
            target = home / ".codex/AGENTS.md"
            target.parent.mkdir(parents=True)
            target.write_text("user-owned\n", encoding="utf-8")
            install(
                package,
                home,
                apply=True,
                global_instructions=True,
                claude_alias=False,
                discovery_aliases=False,
            )
            self.assertTrue(target.is_symlink())
            instructions = (home / ".agents/instructions/AGENTS.md").read_text(encoding="utf-8")
            self.assertNotIn("fleet.managed", instructions)

    def test_existing_fleet_worker_keeps_the_primary_owned_registry(self) -> None:
        package = Path(__file__).resolve().parents[2]
        source_registry = json.loads(
            (package / "edit/settings/fleet/machines.json").read_text(encoding="utf-8")
        )
        worker_id = next((
            machine["id"]
            for machine in source_registry["machines"]
            if machine.get("role") == "worker" and machine.get("enabled")
        ), None)
        if worker_id is None:
            self.skipTest("the standalone starter registry has no enrolled worker")
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

    def test_runtime_upgrade_preserves_existing_source_and_command_root(self) -> None:
        package = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "user-home"
            release = root / "downloaded-release"
            home.mkdir()
            shutil.copytree(package, release, symlinks=True)
            install(
                package,
                home,
                apply=True,
                global_instructions=False,
                claude_alias=False,
                discovery_aliases=False,
            )
            report = install(
                release,
                home,
                apply=True,
                global_instructions=False,
                claude_alias=False,
                discovery_aliases=False,
                runtime_upgrade=True,
            )
            self.assertTrue(report["ready"])
            manifest = json.loads(
                (home / ".agents/state/installed.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["source_root"], str(package.resolve()))
            launcher = (home / ".local/bin/fleet").read_text(encoding="utf-8")
            self.assertIn(f"--root {json.dumps(str(package.resolve()))}", launcher)


if __name__ == "__main__":
    unittest.main()
