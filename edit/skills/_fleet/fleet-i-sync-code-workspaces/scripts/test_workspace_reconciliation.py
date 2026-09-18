#!/usr/bin/env python3
"""Disposable-fixture tests for Code workspace relocation and history."""

from __future__ import annotations

import importlib.util
import io
import json
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIRECTORY = Path(__file__).resolve().parent


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_DIRECTORY / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


controller = load_module("workspace_controller", "sync_code_workspaces.py")
worker = load_module("workspace_worker", "code_workspace_target_worker.py")


def run(*command: str) -> None:
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class WorkspaceReconciliationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.code_root = self.root / "Code"
        self.code_root.mkdir()
        self.code_root = self.code_root.resolve()
        self.remote_url = "https://example.com/acme/repository.git"
        self.remote_identity = "example.com/acme/repository"
        bare = self.root / "origin.git"
        seed = self.root / "seed"
        run("git", "init", "--bare", "--initial-branch=main", str(bare))
        run("git", "clone", str(bare), str(seed))
        run("git", "-C", str(seed), "config", "user.email", "test@example.com")
        run("git", "-C", str(seed), "config", "user.name", "Test")
        run("git", "-C", str(seed), "commit", "--allow-empty", "-m", "initial")
        run("git", "-C", str(seed), "push", "origin", "HEAD:main")
        self.bare = bare

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def clone(self, relative: str) -> Path:
        destination = self.code_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        run("git", "clone", "--branch", "main", str(self.bare), str(destination))
        run("git", "-C", str(destination), "remote", "set-url", "origin", self.remote_url)
        return destination

    def source(self, relative: str) -> dict[str, object]:
        return {
            "relative_path": relative,
            "remote_url": self.remote_url,
            "remote_display": self.remote_url,
            "remote_identity": self.remote_identity,
            "clone_mode": "partial",
            "codex_project_root": ".",
        }

    def reconcile(self, relative: str, *, apply: bool, run_id: str, allow_dirty: bool = False) -> dict[str, object]:
        source = self.source(relative)
        destination = self.code_root / relative
        return worker.bootstrap_repository(
            self.code_root,
            destination,
            source,
            apply,
            worker.repository_inventory(self.code_root),
            {destination},
            set(),
            allow_dirty,
        )

    def test_move_is_idempotent_and_history_is_bounded_state(self) -> None:
        old = self.clone("old/repository")
        preview = self.reconcile("new/repository", apply=False, run_id="preview")
        self.assertEqual(preview["status"], "planned-move")
        self.assertFalse((self.code_root / ".workspace-sync").exists())

        moved = self.reconcile("new/repository", apply=True, run_id="run-1")
        self.assertEqual(moved["status"], "moved")
        self.assertFalse(old.exists())
        destination = self.code_root / "new/repository"
        self.assertTrue((destination / ".git").is_dir())
        history = worker.record_target_run(
            self.code_root,
            "target",
            "source",
            "run-1",
            "reconcile",
            [self.source("new/repository")],
            [moved],
        )
        self.assertTrue(history["recorded"])

        repeated = self.reconcile("new/repository", apply=True, run_id="run-2")
        self.assertEqual(repeated["status"], "already-present")
        state = json.loads((self.code_root / ".workspace-sync/state.json").read_text())
        self.assertEqual(state["observed_repositories"][0]["relative_path"], "new/repository")
        state_root = self.code_root / ".workspace-sync"
        self.assertEqual(stat.S_IMODE(state_root.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((state_root / "state.json").stat().st_mode), 0o600)

    def test_dirty_relocation_requires_explicit_override(self) -> None:
        old = self.clone("old/repository")
        (old / "untracked.txt").write_text("local work\n", encoding="utf-8")
        blocked = self.reconcile("new/repository", apply=True, run_id="run-1")
        self.assertEqual(blocked["status"], "blocked")
        moved = self.reconcile("new/repository", apply=True, run_id="run-2", allow_dirty=True)
        self.assertEqual(moved["status"], "moved")
        self.assertTrue((self.code_root / "new/repository/untracked.txt").is_file())

    def test_reconcile_refreshes_existing_clean_repository(self) -> None:
        destination = self.clone("repository")
        source = self.source("repository")
        refreshed = {"path": "repository", "status": "already-current", "detail": "current branch main"}
        with mock.patch.object(worker, "refresh_repository", return_value=refreshed) as refresh:
            result = worker.bootstrap_repository(
                self.code_root,
                destination,
                source,
                True,
                worker.repository_inventory(self.code_root),
                {destination},
                set(),
                False,
                refresh_existing=True,
            )
        self.assertEqual(result, refreshed)
        refresh.assert_called_once_with(destination, source, True)

    def test_reconcile_refreshes_clean_checkout_after_move(self) -> None:
        old = self.clone("old/repository")
        destination = self.code_root / "new/repository"
        source = self.source("new/repository")
        refreshed = {"path": "new/repository", "status": "fast-forwarded", "detail": "advanced 2 commit(s) on main"}
        with mock.patch.object(worker, "refresh_repository", return_value=refreshed) as refresh:
            result = worker.bootstrap_repository(
                self.code_root,
                destination,
                source,
                True,
                worker.repository_inventory(self.code_root),
                {destination},
                set(),
                False,
                refresh_existing=True,
            )
        self.assertFalse(old.exists())
        self.assertEqual(result["status"], "moved-and-refreshed")
        refresh.assert_called_once_with(destination, source, apply=True)

    def test_reconcile_blocks_dirty_existing_repository(self) -> None:
        destination = self.clone("repository")
        (destination / "local.txt").write_text("work\n", encoding="utf-8")
        result = worker.bootstrap_repository(
            self.code_root,
            destination,
            self.source("repository"),
            True,
            worker.repository_inventory(self.code_root),
            {destination},
            set(),
            False,
            refresh_existing=True,
        )
        self.assertEqual(result["status"], "blocked")

    def test_disabled_target_requires_explicit_single_target_flag(self) -> None:
        registry = {
            "machines": [
                {"id": "source", "enabled": True},
                {
                    "id": "new-worker",
                    "display_name": "New Worker",
                    "enabled": False,
                    "transport": "ssh",
                    "ssh_alias": "new-worker",
                    "home": "/srv/example-linux/test",
                },
            ]
        }
        with self.assertRaisesRegex(RuntimeError, "is disabled"):
            controller.resolve_targets(registry, "source", ["new-worker"])
        selected = controller.resolve_targets(
            registry,
            "source",
            ["new-worker"],
            provision_disabled=True,
        )
        self.assertEqual([machine["id"] for machine in selected], ["new-worker"])
        with self.assertRaisesRegex(RuntimeError, "exactly one explicit"):
            controller.resolve_targets(registry, "source", [], provision_disabled=True)

    def test_machine_registry_loader_accepts_newer_schema_when_required_fields_remain(self) -> None:
        registry_path = self.root / "machines.json"
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 99,
                    "primary_machine_id": "source",
                    "machines": [{"id": "source"}],
                }
            ),
            encoding="utf-8",
        )
        self.assertEqual(controller.load_machines(registry_path)["schema_version"], 99)

    def test_multiple_matching_checkouts_are_ambiguous(self) -> None:
        self.clone("one/repository")
        self.clone("two/repository")
        result = self.reconcile("new/repository", apply=False, run_id="preview")
        self.assertEqual(result["status"], "conflict")
        self.assertIn("multiple existing checkouts", str(result["detail"]))

    def test_linked_worktrees_block_plain_directory_relocation(self) -> None:
        old = self.clone("old/repository")
        run("git", "-C", str(old), "worktree", "add", "-b", "linked", str(self.root / "linked-worktree"))
        result = self.reconcile("new/repository", apply=True, run_id="run-1")
        self.assertEqual(result["status"], "blocked")
        self.assertIn("linked Git worktrees", str(result["detail"]))
        self.assertTrue(old.is_dir())

    def test_exact_entry_move_can_be_detected_and_adopted(self) -> None:
        actual = self.clone("new/repository")
        old = self.code_root / "old/repository"
        catalog_path = self.root / "repositories.json"
        catalog_path.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "entries": {
                        "repository": {
                            "path": "old/repository",
                            "discovery": "repository",
                            "remote": self.remote_url,
                        }
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        spec = controller.normalize_spec(
            "repository",
            {"path": "old/repository", "discovery": "repository", "remote": self.remote_url},
            {"profiles": ["core"], "machines": ["*"], "clone_mode": "partial"},
        )
        repositories, skipped = controller.discover_specs([spec], self.code_root)
        self.assertFalse(skipped)
        self.assertEqual(repositories[0]["relative_path"], actual.relative_to(self.code_root).as_posix())
        self.assertTrue(repositories[0]["source_relocated"])
        changes = controller.adopt_source_layout(catalog_path, self.code_root, repositories)
        self.assertEqual(changes[0]["entry"], "repository")
        adopted = json.loads(catalog_path.read_text(encoding="utf-8"))
        self.assertEqual(adopted["entries"]["repository"]["path"], "new/repository")

    def test_source_history_correlates_target_results(self) -> None:
        source = self.source("repository")
        source.update(
            {
                "entry_id": "repository",
                "source_present": True,
                "remote_display": self.remote_url,
                "machines": ["*"],
                "project_relative_path": "repository",
            }
        )
        history = controller.record_source_run(
            self.code_root,
            "source",
            "run-source",
            "reconcile",
            [source],
            [{"id": "target", "ok": True, "results": [{"path": "repository", "status": "moved"}]}],
        )
        self.assertTrue(history["recorded"])
        run_record = json.loads((self.code_root / ".workspace-sync/runs/run-source.json").read_text())
        self.assertEqual(run_record["targets"][0]["results"][0]["status"], "moved")
        ignored = self.code_root / ".ctx9/should-not-be-discovered"
        run("git", "init", str(ignored))
        self.assertNotIn(ignored, controller.recursive_repositories(self.code_root))
        self.assertNotIn(ignored, worker.recursive_repositories(self.code_root))

        workspace_sync = self.code_root / ".workspace-sync/should-not-be-discovered"
        run("git", "init", str(workspace_sync))
        self.assertNotIn(workspace_sync, controller.recursive_repositories(self.code_root))
        self.assertNotIn(workspace_sync, worker.recursive_repositories(self.code_root))

    def test_runtime_state_migration_is_atomic_and_rejects_conflicts(self) -> None:
        legacy_root = self.code_root / ".ctx9/workspace-bootstrap"
        legacy_root.mkdir(parents=True)
        (legacy_root / "state.json").write_text("{}\n", encoding="utf-8")

        state_root = controller.migrate_runtime_state(self.code_root)
        self.assertEqual(state_root, self.code_root / ".workspace-sync")
        self.assertTrue((state_root / "state.json").is_file())
        self.assertFalse((self.code_root / ".ctx9").exists())
        self.assertEqual(stat.S_IMODE(state_root.stat().st_mode), 0o700)

        legacy_root.mkdir(parents=True)
        with self.assertRaises(RuntimeError):
            controller.migrate_runtime_state(self.code_root)
        with self.assertRaises(ValueError):
            worker.migrate_runtime_state(self.code_root)

    def test_noninteractive_remote_preflight_checks_every_repository(self) -> None:
        reachable = self.source("reachable")
        reachable["remote_url"] = str(self.bare)
        reachable["clone_branch"] = "main"
        blocked = self.source("blocked")
        blocked["remote_url"] = str(self.root / "absent.git")
        report = worker.preflight_repositories([reachable, blocked])
        self.assertFalse(report["ok"])
        self.assertEqual([result["status"] for result in report["results"]], ["reachable", "blocked"])

    def test_remote_transport_preview_apply_and_idempotency(self) -> None:
        destination = self.clone("repository")
        source = self.source("repository")
        source["remote_url"] = "git@example.com:acme/repository.git"

        preview = worker.reconcile_remote(destination, source, apply=False)
        self.assertEqual(preview["status"], "planned-remote-update")
        self.assertEqual(
            subprocess.run(
                ["git", "-C", str(destination), "config", "--local", "--get", "remote.origin.url"],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            ).stdout.strip(),
            self.remote_url,
        )

        real_run = worker.run

        def reachable(command, **kwargs):
            if command[:2] == ["git", "ls-remote"]:
                return subprocess.CompletedProcess(command, 0, "abc\tHEAD\n", "")
            return real_run(command, **kwargs)

        with mock.patch.object(worker, "run", side_effect=reachable):
            applied = worker.reconcile_remote(destination, source, apply=True)
            second = worker.reconcile_remote(destination, source, apply=True)
        self.assertEqual(applied["status"], "remote-updated")
        self.assertEqual(second["status"], "transport-current")

    def test_remote_transport_verification_failure_rolls_back(self) -> None:
        destination = self.clone("repository")
        source = self.source("repository")
        source["remote_url"] = "git@example.com:acme/repository.git"
        real_run = worker.run

        def unreachable(command, **kwargs):
            if command[:2] == ["git", "ls-remote"]:
                return subprocess.CompletedProcess(command, 2, "", "access denied")
            return real_run(command, **kwargs)

        with mock.patch.object(worker, "run", side_effect=unreachable):
            result = worker.reconcile_remote(destination, source, apply=True)
        self.assertEqual(result["status"], "error")
        self.assertTrue(result["rolled_back"])
        self.assertEqual(worker.configured_remote_url(destination, "origin"), self.remote_url)

    def test_failed_apply_preflight_creates_no_target_state(self) -> None:
        absent_code_root = self.root / "new-code-root"
        payload = {
            "operation": "reconcile",
            "apply": True,
            "target_root": str(absent_code_root),
            "repositories": [self.source("repository")],
            "machine_id": "target",
            "source_machine_id": "source",
            "run_id": "blocked-run",
        }
        output_buffer = io.StringIO()
        blocked = {
            "ok": False,
            "results": [{"path": "repository", "status": "blocked", "detail": "no noninteractive access"}],
        }
        with (
            mock.patch.object(worker, "preflight_repositories", return_value=blocked),
            mock.patch.object(worker, "prerequisites", return_value={"git": "git", "codex": "codex", "codex_auth": "authenticated"}),
            mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))),
            mock.patch.object(sys, "stdout", output_buffer),
        ):
            self.assertEqual(worker.main(), 0)
        response = json.loads(output_buffer.getvalue())
        self.assertFalse(response["applied"])
        self.assertIsNone(response["history"])
        self.assertFalse(absent_code_root.exists())

    def test_target_remote_path_uses_registered_terminal_profile(self) -> None:
        machine = {"id": "worker", "terminal_profile": {"remote_path": "/custom/bin:/usr/bin:/bin"}}
        self.assertEqual(controller.target_environment_path(machine), "/custom/bin:/usr/bin:/bin")
        with self.assertRaises(RuntimeError):
            controller.target_environment_path({"id": "worker", "terminal_profile": {"remote_path": "relative:/bin"}})

    def test_target_worker_discovers_macos_gui_ssh_agent(self) -> None:
        machine = {"id": "worker", "terminal_profile": {"remote_path": "/custom/bin:/usr/bin:/bin"}}
        command = controller.target_python_command(machine, "print('ready')")
        self.assertIn("export PATH=/custom/bin:/usr/bin:/bin", command)
        self.assertIn("gui/$(id -u)/com.openssh.ssh-agent", command)
        self.assertIn('export SSH_AUTH_SOCK="$ctx9_agent_socket"', command)

    def test_git_environment_disables_terminal_and_gui_prompts(self) -> None:
        environment = worker.noninteractive_git_environment()
        self.assertEqual(environment["GIT_TERMINAL_PROMPT"], "0")
        self.assertEqual(environment["GCM_INTERACTIVE"], "Never")
        self.assertEqual(environment["GIT_ASKPASS"], "/usr/bin/false")
        self.assertEqual(environment["SSH_ASKPASS_REQUIRE"], "never")
        self.assertIn("BatchMode=yes", environment["GIT_SSH_COMMAND"])

    def test_fleet_plugin_preflight_failure_prevents_every_apply(self) -> None:
        source_root = self.root / "source-code"
        source_root.mkdir()
        args = mock.Mock(
            command="reconcile",
            source_root=source_root,
            catalog=None,
            profile=None,
            entry=[],
            path=[],
            json=False,
            apply=True,
            target=[],
            machine_registry=None,
            provision_disabled=False,
            skip_personal_configuration=False,
            allow_remote_only_source=True,
            allow_dirty_relocation=False,
            adopt_source_layout=False,
        )
        repository = {
            "entry_id": "repository",
            "relative_path": "repository",
            "catalog_relative_path": "repository",
            "remote_url": self.remote_url,
            "remote_display": self.remote_url,
            "remote_identity": self.remote_identity,
            "project_relative_path": "repository",
            "machines": ["*"],
            "dirty": False,
            "ahead": 0,
        }
        targets = [
            {
                "id": "first",
                "display_name": "First",
                "home": "/srv/example-linux/first",
                "platform": "linux",
                "global_agents_eligible": True,
            },
            {
                "id": "second",
                "display_name": "Second",
                "home": "/srv/example-linux/second",
                "platform": "linux",
                "global_agents_eligible": True,
            },
        ]
        inventory = {
            "schema_version": 1,
            "source_cli_version": "codex-cli test",
            "plugins": [
                {
                    "plugin_id": "runtime@test",
                    "name": "runtime",
                    "marketplace": "test",
                    "version": "1",
                    "enabled": True,
                    "source_type": "runtime",
                    "authentication_policy": "NONE",
                }
            ],
        }

        def plugin_preview(machine, *_args, **kwargs):
            self.assertFalse(kwargs["apply"])
            self.assertTrue(kwargs["preflight_only"])
            if machine["id"] == "second":
                return {"ok": False, "ready": False, "applied": False, "error": "Codex plugin CLI unavailable"}
            return {"ok": True, "ready": True, "applied": False, "preflight": {"ok": True, "checks": []}}

        workspace_preview = {
            "ok": True,
            "ready": True,
            "applied": False,
            "preflight": {"ok": True, "results": []},
            "results": [],
            "project_paths": [],
        }
        agent_preview = {"ok": True, "ready": True, "applied": False, "results": []}
        source_preview = {"ok": True, "ready": True, "applied": False, "results": []}
        source_plugin_preview = {
            "ok": True,
            "ready": True,
            "applied": False,
            "preflight": {"ok": True, "checks": []},
            "marketplaces": [],
            "plugins": [],
        }
        with (
            mock.patch.object(controller, "parse_args", return_value=args),
            mock.patch.object(controller, "vault_root", return_value=self.root),
            mock.patch.object(controller, "current_machine_id", return_value="primary"),
            mock.patch.object(controller, "load_catalog", return_value={}),
            mock.patch.object(controller, "select_specs", return_value=([{}], "test")),
            mock.patch.object(controller, "discover_specs", return_value=([repository], [])),
            mock.patch.object(controller, "source_warnings", return_value=[]),
            mock.patch.object(
                controller,
                "load_machines",
                return_value={"primary_machine_id": "primary", "machines": targets},
            ),
            mock.patch.object(controller, "resolve_targets", return_value=targets),
            mock.patch.object(controller.agent_configuration, "load_source_bundle", return_value={}),
            mock.patch.object(controller.agent_configuration, "reconcile_source_alias", return_value=source_preview) as source_alias,
            mock.patch.object(controller.agent_configuration, "invoke_target", return_value=agent_preview) as agent_target,
            mock.patch.object(controller.plugin_reconciliation, "build_desired_inventory", return_value=inventory),
            mock.patch.object(controller.plugin_reconciliation, "reconcile", return_value=source_plugin_preview) as source_plugins,
            mock.patch.object(controller, "invoke_target", return_value=workspace_preview) as workspace_target,
            mock.patch.object(controller, "invoke_plugin_target", side_effect=plugin_preview) as plugin_target,
            mock.patch.object(sys, "stdout", io.StringIO()),
        ):
            self.assertEqual(controller.main(), 1)

        self.assertTrue(all(not call.kwargs["apply"] for call in agent_target.call_args_list))
        self.assertTrue(all(not call.args[3] for call in workspace_target.call_args_list))
        self.assertTrue(all(not call.kwargs["apply"] for call in plugin_target.call_args_list))
        self.assertTrue(all(not call.kwargs["apply"] for call in source_alias.call_args_list))
        self.assertTrue(all(not call.args[0]["apply"] for call in source_plugins.call_args_list))
        self.assertFalse((source_root / ".workspace-sync").exists())


if __name__ == "__main__":
    unittest.main()
