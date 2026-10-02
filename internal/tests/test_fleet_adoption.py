from __future__ import annotations

import copy
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout, redirect_stderr
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import fleet_adoption
import fleet_update
import sync_agents


class AdoptionJourney(unittest.TestCase):
    def fixture(self, root: Path):
        agents = root / "agents"
        (agents / "edit").mkdir(parents=True)
        (agents / "internal/defaults").mkdir(parents=True)
        source = Path(__file__).resolve().parents[1] / "defaults/dependencies.json"
        dependency = copy.deepcopy(next(item for item in json.loads(source.read_text())["dependencies"] if item["id"] == "secret-bindings"))
        dependency["requires"] = []
        manifest = {"schema_version": 2, "dependencies": [dependency]}
        path = agents / "internal/defaults/dependencies.json"
        path.write_text(json.dumps(manifest, indent=2) + "\n")
        machines = [{"id": machine_id, "display_name": machine_id, "role": "primary" if machine_id == "primary" else "worker", "platform": "linux", "enabled": True, "vault": {}} for machine_id in ("primary", "worker-a", "worker-b")]
        registry = {"primary_machine_id": "primary", "machines": machines}
        with mock.patch.object(fleet_update.agent_configuration, "vault_root", return_value=agents):
            args = fleet_update.parse_args(["update", "--dependency", "secret-bindings", "--version", "1.6.6", "--root", str(agents), "--home", str(root / "home")])
        return args, path, registry, machines

    def bind(self, stack: ExitStack, registry, worker):
        configuration = fleet_update.agent_configuration
        stack.enter_context(mock.patch.object(configuration, "load_registry", return_value=registry))
        stack.enter_context(mock.patch.object(configuration, "current_machine_id", return_value="primary"))
        stack.enter_context(mock.patch.object(configuration, "resolve_targets", side_effect=lambda registry, source_id, ids, **kwargs: [item for item in registry["machines"] if item["id"] != source_id and (not ids or item["id"] in ids)]))
        stack.enter_context(mock.patch.object(sync_agents, "validate_machine_secrets"))
        stack.enter_context(mock.patch.object(sync_agents, "validate_dependency_lifecycle_routes"))
        stack.enter_context(mock.patch.object(sync_agents, "build_agent_reference_files", return_value={}))
        stack.enter_context(mock.patch.object(sync_agents, "write_aggregate_lock"))
        stack.enter_context(mock.patch.object(sync_agents, "invoke_portable_worker", side_effect=worker))
        stack.enter_context(redirect_stdout(io.StringIO()))
        stack.enter_context(redirect_stderr(io.StringIO()))

    def test_partial_adoption_resumes_same_request_and_preserves_concurrent_source(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            args, manifest_path, registry, machines = self.fixture(root)
            versions = {item["id"]: "1.5.2" for item in machines}
            installs = []
            fail_once = True
            change_source = False
            fail_final_verify = False
            drift_after_preview = False
            sources = {item["id"]: "a" * 40 for item in machines}
            catalogs = {item["id"]: "c" * 64 for item in machines}

            def worker(machine, module, payload, **kwargs):
                nonlocal fail_once
                machine_id = machine["id"]
                desired = payload["manifest"]["dependencies"][0]["contract"]["verify"]["exact"]
                expected = payload["expected_releases"].get("secret-bindings")
                if expected is not None and (expected["source_commit"] != sources[machine_id] or expected["catalog_sha256"] != catalogs[machine_id]):
                    return {"id": machine_id, "ok": True, "ready": False, "can_apply": False, "outcome_known": True, "preflight": [{"id": "secret-bindings", "installable": False, "detail": "release-changed"}], "packages": [], "reference_package": {"changes": [], "collisions": []}}
                if payload["mode"] == "apply":
                    installs.append(machine_id)
                    if machine_id == "worker-b" and fail_once:
                        fail_once = False
                        return {"id": machine_id, "ok": False, "error": "synthetic sensitive diagnostic", "outcome_known": True}
                    versions[machine_id] = desired
                    if change_source:
                        current = json.loads(manifest_path.read_text())
                        current["concurrent_note"] = "must remain"
                        manifest_path.write_text(json.dumps(current))
                ready = versions[machine_id] == desired
                recorded = json.loads(manifest_path.read_text())["dependencies"][0]["contract"]["verify"]["exact"]
                if fail_final_verify and payload["mode"] == "verify" and recorded == "1.6.7":
                    ready = False
                report = {"id": machine_id, "ok": True, "ready": ready, "can_apply": True, "outcome_known": True, "preflight": [{"id": "secret-bindings", "installable": True, "release": {"component": "secret-bindings", "version": desired, "source_commit": sources[machine_id], "catalog_sha256": catalogs[machine_id]}}], "packages": [{"id": "secret-bindings", "ready": ready}], "reference_package": {"ready": True, "changes": [], "collisions": []}}
                if drift_after_preview and payload["mode"] == "dry-run" and machine_id == "worker-b":
                    catalogs.update({key: "e" * 64 for key in catalogs})
                return report

            self.bind(stack, registry, worker)
            original = manifest_path.read_bytes()
            preview = copy.copy(args)
            preview.dry_run = True
            self.assertEqual(fleet_update.update(preview), 0)
            self.assertFalse(args.home.exists())
            self.assertEqual(manifest_path.read_bytes(), original)
            sources["worker-b"] = "b" * 40
            with self.assertRaisesRegex(fleet_adoption.AdoptionError, "adoption-release-changed"):
                fleet_update.update(preview)
            self.assertFalse(args.home.exists())
            self.assertFalse(installs)
            sources["worker-b"] = "a" * 40
            catalogs["worker-b"] = "d" * 64
            with self.assertRaisesRegex(fleet_adoption.AdoptionError, "adoption-release-changed"):
                fleet_update.update(preview)
            self.assertFalse(args.home.exists())
            self.assertFalse(installs)
            catalogs["worker-b"] = "c" * 64
            with self.assertRaises(sync_agents.AgentsSyncError):
                fleet_update.update(args)
            self.assertEqual(installs, ["worker-a", "worker-b"])
            self.assertEqual(versions["primary"], "1.5.2")
            self.assertEqual(manifest_path.read_bytes(), original)
            journal_root = args.home / ".agents/state/fleet-updates"
            active = fleet_adoption.read_state(journal_root / "active.json")
            operation = active["operation"]
            journal = fleet_adoption.read_state(journal_root / f"{operation}.json")
            self.assertEqual(journal["stage"], "partial")
            self.assertEqual(journal["targets"]["worker-a"]["status"], "ready")
            self.assertEqual(journal["release"]["source_commit"], "a" * 40)
            self.assertNotIn("sensitive", json.dumps(journal))
            for item in journal_root.iterdir():
                self.assertEqual(item.stat().st_mode & 0o777, 0o600)
            # Resume cannot adopt a different signed source at the same version.
            sources.update({key: "b" * 40 for key in sources})
            self.assertEqual(fleet_update.update(args), 1)
            self.assertEqual(installs, ["worker-a", "worker-b"])
            self.assertEqual(manifest_path.read_bytes(), original)
            self.assertEqual(fleet_adoption.read_state(journal_root / f"{operation}.json")["release"]["source_commit"], "a" * 40)
            sources.update({key: "a" * 40 for key in sources})
            catalogs.update({key: "d" * 64 for key in catalogs})
            self.assertEqual(fleet_update.update(args), 1)
            self.assertEqual(installs, ["worker-a", "worker-b"])
            self.assertEqual(manifest_path.read_bytes(), original)
            catalogs.update({key: "c" * 64 for key in catalogs})
            self.assertEqual(fleet_update.update(args), 0)
            self.assertEqual(installs, ["worker-a", "worker-b", "worker-b", "primary"])
            self.assertEqual(fleet_adoption.read_state(journal_root / "active.json")["operation"], operation)
            self.assertEqual(fleet_adoption.read_state(journal_root / f"{operation}.json")["stage"], "complete")
            after = manifest_path.read_bytes()
            self.assertEqual(fleet_update.update(args), 0)
            self.assertEqual(manifest_path.read_bytes(), after)
            self.assertEqual(len(installs), 4)
            # A target-scoped canary must not silently activate the primary or another worker.
            args.target = ["worker-a"]
            versions["worker-a"] = "1.5.2"
            self.assertEqual(fleet_update.update(args), 0)
            self.assertEqual(installs[-1], "worker-a")
            self.assertEqual(len(installs), 5)
            # A topology change between request resolution and execution is denied before activation.
            resolved = copy.deepcopy(registry)
            resolved["changed_policy"] = True
            with mock.patch.object(fleet_update.agent_configuration, "load_registry", side_effect=[registry, resolved]):
                with self.assertRaises(fleet_adoption.AdoptionError):
                    fleet_update.update(args)
            self.assertEqual(len(installs), 5)
            # Activation and recording can succeed while the final live verification fails.
            args.target = []
            args.version = "1.6.7"
            fail_final_verify = True
            self.assertEqual(fleet_update.update(args), 2)
            failed_record = fleet_adoption.read_state(journal_root / "active.json")
            self.assertEqual(failed_record["stage"], "verification-failed")
            self.assertEqual(json.loads(manifest_path.read_text())["dependencies"][0]["contract"]["verify"]["exact"], "1.6.7")
            after_installs = len(installs)
            fail_final_verify = False
            self.assertEqual(fleet_update.update(args), 0)
            self.assertEqual(len(installs), after_installs)
            self.assertEqual(fleet_adoption.read_state(journal_root / "active.json")["operation"], failed_record["operation"])
            # Catalog drift after an accepted preview is caught before any target activates.
            args.version = "1.6.8"
            drift_after_preview = True
            before_drift = manifest_path.read_bytes()
            self.assertEqual(fleet_update.update(args), 1)
            self.assertEqual(len(installs), after_installs)
            self.assertEqual(manifest_path.read_bytes(), before_drift)
            drift_after_preview = False
            catalogs.update({key: "c" * 64 for key in catalogs})
            self.assertEqual(fleet_update.update(args), 0)
            # A concurrent source edit is not overwritten after target activation.
            args.target = []
            versions["worker-b"] = "1.5.2"
            change_source = True
            with self.assertRaises(fleet_update.FleetUpdateError):
                fleet_update.update(args)
            self.assertEqual(json.loads(manifest_path.read_text())["concurrent_note"], "must remain")
            self.assertEqual(fleet_adoption.read_state(journal_root / "active.json")["stage"], "recording-conflict")

    def test_live_lock_and_unknown_interruption_never_start_a_second_apply(self):
        invoke_worker = sync_agents.invoke_portable_worker
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            args, manifest_path, registry, machines = self.fixture(root)
            calls = []

            def worker(machine, module, payload, **kwargs):
                calls.append((machine["id"], payload["mode"]))
                if payload["mode"] == "apply":
                    raise KeyboardInterrupt
                return {"id": machine["id"], "ok": True, "ready": False, "can_apply": True, "preflight": [{"id": "secret-bindings", "installable": True, "release": {"component": "secret-bindings", "version": "1.6.6", "source_commit": "a" * 40, "catalog_sha256": "c" * 64}}], "packages": [], "reference_package": {"changes": [], "collisions": []}}

            self.bind(stack, registry, worker)
            original = manifest_path.read_bytes()
            with self.assertRaises(KeyboardInterrupt):
                fleet_update.update(args)
            journal_root = args.home / ".agents/state/fleet-updates"
            self.assertEqual(fleet_adoption.read_state(journal_root / "active.json")["stage"], "outcome-unknown")
            count = len(calls)
            with self.assertRaises(fleet_adoption.AdoptionError):
                fleet_update.update(args)
            self.assertEqual(len(calls), count)
            self.assertEqual(manifest_path.read_bytes(), original)
            # Losing the transport/report never certifies that remote installer children exited.
            lost = subprocess.CompletedProcess([], 255, "", "synthetic sensitive transport error")
            with mock.patch.object(sync_agents.subprocess, "run", return_value=lost):
                report = invoke_worker({"id": "worker-a"}, fleet_update.dependency_worker, {}, local=True)
            self.assertFalse(report["outcome_known"])
            self.assertNotIn("sensitive", json.dumps(report))
            with fleet_adoption.adoption_lock(root / "lost-response-home", {"schema_version": 1, "targets": ["worker-a"]}) as adoption:
                adoption.stage("applying")
                adoption.target("apply", "started", {"id": "worker-a"})
                adoption.target("apply", "finished", report)
                adoption.interrupted()
                self.assertEqual(adoption.state["stage"], "outcome-unknown")
            unknown_success = {"id": "worker-a", "ok": True, "ready": True, "outcome_known": False}
            with mock.patch.object(sync_agents, "invoke_portable_worker", return_value=unknown_success):
                reports = sync_agents.invoke_dependency_targets([{"id": "worker-a"}, {"id": "worker-b"}], {}, {}, source_id="primary", mode="apply")
            self.assertEqual(len(reports), 1)
            self.assertFalse(reports[0]["outcome_known"])
            # A real live owner holds the OS lock, not a stale PID convention.
            home = root / "other-home"
            request = {"schema_version": 1, "targets": ["primary"]}
            with fleet_adoption.adoption_lock(home, request):
                with self.assertRaises(fleet_adoption.AdoptionError):
                    with fleet_adoption.adoption_lock(home, request):
                        self.fail("second owner acquired the lock")


if __name__ == "__main__":
    unittest.main()
