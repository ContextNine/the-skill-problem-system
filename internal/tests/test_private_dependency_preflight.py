from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import dependency_worker as worker


class PrivateDependencyJourney(unittest.TestCase):
    def test_ready_installs_still_check_exact_authority_without_mutation(self) -> None:
        source = Path(__file__).resolve().parents[1] / "defaults/dependencies.json"
        dependency = copy.deepcopy(next(item for item in json.loads(source.read_text())["dependencies"] if item["id"] == "secret-bindings"))
        dependency["requires"] = []
        for recipe in dependency["contract"]["recipes"].values():
            recipe["provenance_project"] = "example/fixture"
        payload = {"mode": "dry-run", "manifest": {"schema_version": 2, "dependencies": [dependency]}}
        ready = {"id": "secret-bindings", "ready": True, "detail": "verified"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            cli = bin_dir / "ctx9"
            cli.write_text(
                "#!/usr/bin/env python3\nimport json,os,sys\n"
                "args=sys.argv[1:]\n"
                "assert 'preflight' in args or 'install' in args\n"
                "assert args[args.index('--provenance-project')+1]=='example/fixture'\n"
                "assert args[args.index('--expected-version')+1]=='1.5.2'\n"
                "state=os.environ['FIXTURE_STATE']\n"
                "if 'install' in args:\n"
                " assert args[args.index('--expected-source-commit')+1]=='a'*40\n"
                " assert args[args.index('--expected-catalog-sha256')+1]=='c'*64\n"
                " print(json.dumps({'ready':False,'state':'release-changed'}));sys.exit(1)\n"
                "if state=='malformed':\n print('sensitive provider output');sys.exit(1)\n"
                "report={'schema_version':1,'ready':state=='ready','state':state,'trust_verified':state=='ready','values_returned':False,'component':'secret-bindings','version':'1.5.2','source_commit':'a'*40,'catalog_sha256':'c'*64,'platform':'linux','architecture':'x86_64'}\n"
                "if state=='wrong-version': report.update(ready=True,state='ready',trust_verified=True,version='9.9.9')\n"
                "print(json.dumps(report));sys.exit(0 if report['ready'] else 1)\n"
            )
            cli.chmod(0o755)
            install_package = worker.install_package
            with mock.patch.object(worker.Path, "home", return_value=root), mock.patch.object(worker, "platform_name", return_value="linux"), mock.patch.object(worker, "architecture_name", return_value="x64"), mock.patch.object(worker, "verify_package", return_value=ready), mock.patch.object(worker, "install_package", side_effect=AssertionError("readiness changed the installation")):
                for state in ("credential-locked", "credential-expired", "access-denied", "rate-limited", "verifier-unavailable", "trust-rejected", "wrong-version", "malformed", "ready"):
                    env = {"PATH": str(bin_dir) + os.pathsep + os.defpath, "FIXTURE_STATE": state}
                    with self.subTest(state=state), mock.patch.object(worker, "environment", return_value=env):
                        report = worker.reconcile(payload)
                        self.assertEqual(report["can_apply"], state == "ready")
                        self.assertEqual(report["ready"], state == "ready")
                        self.assertNotIn("sensitive", json.dumps(report))
                        self.assertFalse((root / ".agents").exists())
                        if state != "ready":
                            with self.assertRaises(worker.DependencyError):
                                worker.reconcile({**payload, "mode": "apply"})
                            self.assertFalse((root / ".agents").exists())
                with mock.patch.object(worker, "environment", return_value={"PATH": str(bin_dir) + os.pathsep + os.defpath, "FIXTURE_STATE": "ready"}):
                    for expected in ({"source_commit": "b" * 40, "catalog_sha256": "c" * 64}, {"source_commit": "a" * 40, "catalog_sha256": "d" * 64}):
                        blocked = {**payload, "expected_releases": {"secret-bindings": expected}}
                        self.assertEqual(worker.reconcile(blocked)["preflight"][0]["detail"], "release-changed")
                        with self.assertRaises(worker.DependencyError):
                            worker.reconcile({**blocked, "mode": "apply"})
                        self.assertFalse((root / ".agents").exists())
                    # The real adapter carries both pins to executable installation.
                    with mock.patch.object(worker, "install_package", side_effect=install_package), mock.patch.object(worker, "verify_package", return_value={**ready, "ready": False}), mock.patch.object(worker, "run", wraps=worker.run) as run:
                        with self.assertRaisesRegex(worker.DependencyError, "private-component-install-failed"):
                            worker.reconcile({**payload, "mode": "apply"})
                        arguments = run.call_args.args[0]
                        self.assertEqual(arguments[arguments.index("--expected-source-commit") + 1], "a" * 40)
                        self.assertEqual(arguments[arguments.index("--expected-catalog-sha256") + 1], "c" * 64)
                        self.assertFalse((root / ".agents").exists())
                    self.assertTrue(worker.reconcile({**payload, "mode": "apply"})["ready"])
                    self.assertTrue((root / ".agents/state/dependencies.lock.json").is_file())


if __name__ == "__main__":
    unittest.main()
