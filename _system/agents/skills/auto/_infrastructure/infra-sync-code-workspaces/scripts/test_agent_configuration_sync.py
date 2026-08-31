#!/usr/bin/env python3
"""Focused integration tests for primary-owned agent configuration sync."""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
VAULT_ROOT = SCRIPT_DIRECTORY.parents[6]


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_DIRECTORY / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sync = load_module("agent_configuration_sync", "sync_agent_configuration.py")
WORKER = SCRIPT_DIRECTORY / "agent_configuration_target_worker.py"


class AgentConfigurationSyncTests(unittest.TestCase):
    def create_registry(self) -> dict[str, object]:
        return {
            "schema_version": 99,
            "primary_machine_id": "primary",
            "machines": [
                {
                    "id": "primary",
                    "display_name": "Primary",
                    "enabled": True,
                    "home": "/srv/example-macos/matt",
                    "role": "primary",
                    "platform": "macos",
                    "roots": {"code": "~/code", "vault": "~/Vault"},
                    "vault": {"enabled": True, "checkout_mode": "primary-external-git", "required": True},
                    "machine_access": {
                        "provider": "wireguard",
                        "providers": {"wireguard": {"state": "configured", "host": "10.13.13.2"}},
                    },
                },
                {
                    "id": "worker-mac",
                    "display_name": "Worker Mac",
                    "enabled": True,
                    "home": "/srv/example-macos/matt",
                    "role": "worker",
                    "platform": "macos",
                    "roots": {"code": "~/code", "vault": "~/Vault"},
                    "vault": {"enabled": True, "checkout_mode": "icloud-gitless", "required": True},
                    "machine_access": {
                        "provider": "tailscale",
                        "providers": {"tailscale": {"state": "configured", "host": "worker-mac.example.ts.net"}},
                    },
                },
                {
                    "id": "linux-worker",
                    "display_name": "Linux Worker",
                    "enabled": True,
                    "home": "/srv/example-linux/matt",
                    "role": "worker",
                    "platform": "linux",
                    "roots": {"code": "~/code", "vault": None},
                    "vault": {"enabled": False, "checkout_mode": "none", "required": False},
                    "machine_access": {
                        "provider": "wireguard",
                        "providers": {"wireguard": {"state": "configured", "host": "10.13.13.10"}},
                    },
                    "vnc": {
                        "kind": "ssh-novnc",
                        "open_path": "/vnc.html?autoconnect=1",
                    },
                },
            ],
        }

    def create_source(self, root: Path) -> tuple[Path, dict[str, object]]:
        (root / "AGENTS.md").write_text("Vault instructions.\n", encoding="utf-8")
        source = root / "source"
        (source / ".codex").mkdir(parents=True)
        (source / ".claude").mkdir()
        (source / ".codex/config.toml").write_text(
            f'''model = "gpt-test"
approval_policy = "on-request"
sandbox_mode = "workspace-write"
log_dir = "{source}/logs"

[mcp_servers.computer-use]
enabled = false

[plugins."source-only@paper"]
enabled = true

[marketplaces.paper]
source_type = "git"
source = "https://example.com/source-only.git"
''',
            encoding="utf-8",
        )
        (source / ".claude/settings.json").write_text(
            json.dumps({"model": "test", "hooks": {}, "path": f"{source}/tools"}) + "\n",
            encoding="utf-8",
        )
        config = root / "_system/agents/_package/instance"
        templates = root / "_system/agents/_package/templates/instructions"
        (config / "instructions").mkdir(parents=True)
        (config / "skills").mkdir(parents=True)
        (config / "integrations").mkdir(parents=True)
        (templates / "platform").mkdir(parents=True)
        (templates / "role").mkdir(parents=True)
        (config / "instructions/AGENTS.md").write_text("Keep it simple.\n", encoding="utf-8")
        (config / "integrations/langfuse.json").write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "instance_id": "test",
                    "enabled": True,
                    "base_url": "https://langfuse.example.test",
                    "credential_registry_id": "langfuse-coding-agent-api",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (config / "skills/sources.json").write_text(
            json.dumps({
                "schema_version": 3,
                "repos": [],
                "repository_skills": {},
            }) + "\n",
            encoding="utf-8",
        )
        (config / "instructions/fragments.json").write_text(
            '{"schema_version":1,"install":{},"fragments":[]}\n', encoding="utf-8"
        )
        (templates / "platform/macos.md").write_text("macOS.\n", encoding="utf-8")
        (templates / "platform/linux.md").write_text("Linux.\n", encoding="utf-8")
        (templates / "role/primary.md").write_text("Primary.\n", encoding="utf-8")
        (templates / "role/worker.md").write_text("Worker.\n", encoding="utf-8")
        (templates / "machine.md").write_text(
            "Machine {machine_id} at {service_url}. Code {code_root}. Vault {vault_root}.\n{peers}\n{access_guidance}\n",
            encoding="utf-8",
        )
        return source, self.create_registry()

    def run_worker(self, home: Path, files: list[dict[str, object]], suffix: str) -> dict[str, object]:
        payload = {
            "home": str(home),
            "apply": True,
            "verify": False,
            "backup_suffix": suffix,
            "files": files,
        }
        process = subprocess.run(
            ["python3", str(WORKER)],
            input=json.dumps(payload),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "HOME": str(home)},
            check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr or process.stdout)
        return json.loads(process.stdout)

    def test_shared_worker_supports_inline_remote_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            worker_source = sync.global_agent_configuration.__file__
            assert worker_source
            payload = {
                "home": str(home),
                "apply": False,
                "verify": False,
                "backup_suffix": "preview",
                "files": [],
            }
            process = subprocess.run(
                ["python3", "-c", Path(worker_source).read_text(encoding="utf-8")],
                input=json.dumps(payload),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={**os.environ, "HOME": str(home)},
                check=False,
            )
            self.assertEqual(process.returncode, 0, process.stderr or process.stdout)
            self.assertTrue(json.loads(process.stdout)["ready"])

    def test_worker_mac_sync_is_rebased_atomic_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, registry = self.create_source(root)
            target = root / "target"
            target.mkdir()
            (target / ".codex").mkdir()
            (target / ".codex/config.toml").write_text(
                '''[plugins."target-only@personal"]
enabled = false

[marketplaces.personal]
source_type = "local"
source = "/target/local/marketplace"
''',
                encoding="utf-8",
            )
            bundle = sync.load_source_bundle(source, root=root, registry=registry)
            machine = {
                "id": "worker-mac",
                "home": str(target),
                "role": "worker",
                "platform": "macos",
            }
            files = sync.rendered_files(bundle, machine)
            first = self.run_worker(target, files, "first")
            self.assertTrue(first["ready"])
            config = (target / ".codex/config.toml").read_text(encoding="utf-8")
            self.assertIn('approval_policy = "never"', config)
            self.assertIn('sandbox_mode = "danger-full-access"', config)
            self.assertIn("[mcp_servers.computer-use]\nenabled = true", config)
            self.assertIn('[plugins."target-only@personal"]\nenabled = false', config)
            self.assertIn('[marketplaces.personal]', config)
            self.assertNotIn("source-only@paper", config)
            self.assertNotIn("source-only.git", config)
            self.assertIn(f'log_dir = "{target}/logs"', config)
            self.assertNotIn(str(source), config)
            self.assertEqual(stat.S_IMODE((target / ".codex/config.toml").stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE((target / ".codex/AGENTS.md").stat().st_mode), 0o644)
            self.assertEqual(
                stat.S_IMODE((target / ".config/ctx9/agents/integrations/langfuse.json").stat().st_mode),
                0o600,
            )
            self.assertEqual(
                json.loads((target / ".config/ctx9/agents/integrations/langfuse.json").read_text()),
                {
                    "schema_version": 2,
                    "instance_id": "test",
                    "enabled": True,
                    "base_url": "https://langfuse.example.test",
                    "credential_registry_id": "langfuse-coding-agent-api",
                },
            )
            self.assertTrue((target / ".claude/CLAUDE.md").is_symlink())
            self.assertEqual(os.readlink(target / ".claude/CLAUDE.md"), "../.codex/AGENTS.md")

            (target / ".codex/config.toml").write_text("local drift\n", encoding="utf-8")
            second = self.run_worker(target, files, "second")
            self.assertTrue(second["ready"])
            self.assertTrue((target / ".codex/config.toml.backup-second").is_file())
            third = self.run_worker(target, files, "third")
            self.assertTrue(all(result["status"] == "match" for result in third["results"]))

    def test_role_rendering_uses_registry_addresses_and_linux_novnc_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, registry = self.create_source(root)
            bundle = sync.load_source_bundle(source, root=root, registry=registry)
            rendered = bundle["agents_by_machine"]
            self.assertIn("http://10.13.13.2:<port>", rendered["primary"])
            self.assertIn("http://worker-mac.example.ts.net:<port>", rendered["worker-mac"])
            self.assertIn("http://10.13.13.10:<port>", rendered["linux-worker"])
            self.assertIn("127.0.0.1:61152", rendered["linux-worker"])

    def test_component_selection_filters_settings_and_instructions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, registry = self.create_source(root)
            bundle = sync.load_source_bundle(source, root=root, registry=registry)
            machine = registry["machines"][1]
            config_paths = {
                item["path"] for item in sync.rendered_files(bundle, machine, components={"config"})
            }
            instruction_paths = {
                item["path"]
                for item in sync.rendered_files(bundle, machine, components={"instructions"})
            }
            self.assertEqual(
                config_paths,
                {
                    ".codex/config.toml",
                    ".claude/settings.json",
                    ".config/ctx9/agents/instructions/AGENTS.md",
                    ".config/ctx9/agents/instructions/fragments.json",
                    ".config/ctx9/agents/integrations/langfuse.json",
                    ".config/ctx9/agents/skills/sources.json",
                },
            )
            self.assertEqual(
                instruction_paths,
                {".codex/AGENTS.md", ".claude/CLAUDE.md"},
            )

    def test_config_sync_installs_primary_non_secret_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, registry = self.create_source(root)
            bundle = sync.load_source_bundle(source, root=root, registry=registry)
            with patch.object(Path, "home", return_value=source):
                report = sync.reconcile_source_alias(
                    source,
                    bundle,
                    "primary",
                    root,
                    apply=True,
                    verify=False,
                    backup_suffix="test",
                    components={"config"},
                )
            self.assertTrue(report["ready"])
            metadata = source / ".config/ctx9/agents/integrations/langfuse.json"
            self.assertEqual(stat.S_IMODE(metadata.stat().st_mode), 0o600)
            self.assertFalse((source / ".codex/AGENTS.md").exists())

    def test_config_sync_replaces_stale_bootstrap_workspace_registry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, registry = self.create_source(root)
            desired = root / "_system/agents/_package/instance/fleet/workspaces.json"
            desired.parent.mkdir(parents=True)
            desired.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "default_profile": "core",
                        "entries": {"secret-bindings": {"path": "ctx9/secret-bindings"}},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            installed = source / ".config/ctx9/agents/fleet/workspaces.json"
            installed.parent.mkdir(parents=True)
            installed.write_text(
                '{"schema_version":2,"default_profile":"core","entries":{}}\n',
                encoding="utf-8",
            )
            bundle = sync.load_source_bundle(source, root=root, registry=registry)
            with patch.object(Path, "home", return_value=source):
                report = sync.reconcile_source_alias(
                    source,
                    bundle,
                    "primary",
                    root,
                    apply=True,
                    verify=False,
                    backup_suffix="test",
                    components={"config"},
                )
            self.assertTrue(report["ready"])
            self.assertEqual(json.loads(installed.read_text()), json.loads(desired.read_text()))
            self.assertTrue(installed.with_name("workspaces.json.backup-test").is_file())

    def test_shared_vault_alias_reconciler_is_dry_run_safe_and_refuses_unmanaged_file(self) -> None:
        shared = sync.global_agent_configuration
        sync_spec = importlib.util.spec_from_file_location(
            "sync_skills_shared_agent_test",
            VAULT_ROOT / "_system/agents/_package/src/sync_skills.py",
        )
        assert sync_spec and sync_spec.loader
        regular_sync = importlib.util.module_from_spec(sync_spec)
        sys.modules[sync_spec.name] = regular_sync
        sync_spec.loader.exec_module(regular_sync)
        self.assertIs(
            regular_sync.global_agent_configuration.ensure_agent_paths,
            shared.ensure_agent_paths,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "AGENTS.md").write_text("Vault instructions\n", encoding="utf-8")
            preview = shared.ensure_agent_paths(root, dry_run=True)
            self.assertFalse(preview["ready"])
            self.assertFalse((root / "CLAUDE.md").exists())
            applied = shared.ensure_agent_paths(root, dry_run=False)
            self.assertTrue(applied["ready"])
            self.assertEqual(os.readlink(root / "CLAUDE.md"), "AGENTS.md")
            (root / "CLAUDE.md").unlink()
            (root / "CLAUDE.md").write_text("unmanaged\n", encoding="utf-8")
            with self.assertRaisesRegex(shared.AgentConfigurationError, "unmanaged"):
                shared.ensure_agent_paths(root, dry_run=True)

    def test_registry_consumers_are_forward_compatible_and_inline_secrets_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            registry = root / "machines.json"
            registry.write_text(
                json.dumps(
                    {
                        "schema_version": 99,
                        "primary_machine_id": "primary",
                        "machines": [{"id": "primary"}],
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(sync.load_registry(registry)["schema_version"], 99)

            source, source_registry = self.create_source(root)
            (source / ".claude/settings.json").write_text(
                json.dumps({"env": {"API_TOKEN": "do-not-copy"}}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "credential-like"):
                sync.load_source_bundle(source, root=root, registry=source_registry)


if __name__ == "__main__":
    unittest.main()
