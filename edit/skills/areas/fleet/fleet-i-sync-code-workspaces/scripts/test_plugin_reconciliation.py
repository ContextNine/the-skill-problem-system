#!/usr/bin/env python3
"""Integration tests for portable Codex plugin desired-state reconciliation."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest import mock

import plugin_reconciliation as plugins


def run(*command: str, cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


FAKE_CODEX = r'''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

home = Path(os.environ["HOME"])
state_path = home / "fake-codex-state.json"
actions_path = home / "fake-codex-actions.jsonl"
state = json.loads(state_path.read_text())
args = sys.argv[1:]

def save(action):
    state_path.write_text(json.dumps(state, indent=2) + "\n")
    with actions_path.open("a") as handle:
        handle.write(json.dumps(action) + "\n")

def emit(value):
    print(json.dumps(value))

if args == ["--version"]:
    print("codex-cli 0.test")
elif args[:3] == ["plugin", "marketplace", "list"]:
    broken = any(item["name"] == "paper" and not Path(item["root"]).is_dir() for item in state["marketplaces"])
    if broken:
        print("marketplace manifest missing", file=sys.stderr)
        raise SystemExit(1)
    emit({"marketplaces": state["marketplaces"]})
elif args[:2] == ["plugin", "list"]:
    broken = any(item["name"] == "paper" and not Path(item["root"]).is_dir() for item in state["marketplaces"])
    if broken:
        print("marketplace manifest missing", file=sys.stderr)
        raise SystemExit(1)
    emit({"installed": state["installed"], "available": []})
elif args[:3] == ["plugin", "marketplace", "remove"]:
    name = args[3]
    current = next((item for item in state["marketplaces"] if item["name"] == name), None)
    if current and not Path(current["root"]).is_dir():
        print("marketplace manifest missing", file=sys.stderr)
        raise SystemExit(1)
    state["marketplaces"] = [item for item in state["marketplaces"] if item["name"] != name]
    save({"action": "marketplace-remove", "name": name})
    emit({"removed": name})
elif args[:3] == ["plugin", "marketplace", "add"]:
    source = args[3]
    revision = args[args.index("--ref") + 1] if "--ref" in args else None
    root = home / ".codex/.tmp/marketplaces/paper"
    if root.exists():
        shutil.rmtree(root)
    subprocess.run(["git", "clone", source, str(root)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if revision:
        subprocess.run(["git", "-C", str(root), "checkout", "--detach", revision], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    state["marketplaces"] = [item for item in state["marketplaces"] if item["name"] != "paper"]
    state["marketplaces"].append({
        "name": "paper",
        "root": str(root),
        "marketplaceSource": {"sourceType": "git", "source": source},
    })
    save({"action": "marketplace-add", "name": "paper", "revision": revision})
    emit({"added": "paper"})
elif args[:2] == ["plugin", "add"]:
    plugin_id = args[2]
    state["installed"] = [item for item in state["installed"] if item["pluginId"] != plugin_id]
    state["installed"].append({
        "pluginId": plugin_id,
        "name": plugin_id.split("@", 1)[0],
        "marketplaceName": plugin_id.split("@", 1)[1],
        "version": "0.1.0",
        "installed": True,
        "enabled": True,
    })
    save({"action": "plugin-add", "plugin_id": plugin_id})
    emit({"added": plugin_id})
elif args[:2] == ["plugin", "remove"]:
    plugin_id = args[2]
    state["installed"] = [item for item in state["installed"] if item["pluginId"] != plugin_id]
    save({"action": "plugin-remove", "plugin_id": plugin_id})
    emit({"removed": plugin_id})
else:
    print(f"unsupported fake codex command: {args}", file=sys.stderr)
    raise SystemExit(2)
'''


class PluginReconciliationTests(unittest.TestCase):
    def create_marketplace(self, root: Path) -> tuple[Path, str]:
        source = root / "paper-source"
        (source / ".agents/plugins").mkdir(parents=True)
        (source / ".agents/plugins/marketplace.json").write_text(
            json.dumps({"name": "paper", "plugins": []}) + "\n",
            encoding="utf-8",
        )
        run("git", "init", "--initial-branch=main", str(source))
        run("git", "-C", str(source), "config", "user.email", "test@example.com")
        run("git", "-C", str(source), "config", "user.name", "Test")
        run("git", "-C", str(source), "add", ".")
        run("git", "-C", str(source), "commit", "-m", "paper marketplace")
        revision = subprocess.run(
            ["git", "-C", str(source), "rev-parse", "HEAD"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()
        return source, revision

    def test_broken_marketplace_recovery_is_safe_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            fake_bin = root / "bin"
            fake_bin.mkdir()
            home.mkdir()
            fake_codex = fake_bin / "codex"
            fake_codex.write_text(FAKE_CODEX, encoding="utf-8")
            fake_codex.chmod(0o755)
            source, revision = self.create_marketplace(root)
            broken_root = home / ".codex/.tmp/marketplaces/paper"
            (home / ".codex").mkdir()
            (home / ".codex/config.toml").write_text(
                '''[plugins."paper-desktop@paper"]
enabled = true

[marketplaces.paper]
source_type = "git"
source = "broken"
''',
                encoding="utf-8",
            )
            (home / "fake-codex-state.json").write_text(
                json.dumps(
                    {
                        "marketplaces": [
                            {
                                "name": "paper",
                                "root": str(broken_root),
                                "marketplaceSource": {"sourceType": "git", "source": str(source)},
                            }
                        ],
                        "installed": [
                            {
                                "pluginId": "target-only@local",
                                "name": "target-only",
                                "marketplaceName": "local",
                                "version": "9.9.9",
                                "installed": True,
                                "enabled": True,
                            }
                        ],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            inventory = {
                "schema_version": 1,
                "source_cli_version": "codex-cli 0.test",
                "plugins": [
                    {
                        "plugin_id": "paper-desktop@paper",
                        "name": "paper-desktop",
                        "marketplace": "paper",
                        "version": "0.1.0",
                        "enabled": True,
                        "authentication_policy": "ON_INSTALL",
                        "source_type": "git",
                        "source": str(source),
                        "revision": revision,
                    }
                ],
            }
            payload = {
                "home": str(home),
                "platform": "linux",
                "inventory": inventory,
                "planned_repositories": [],
                "apply": True,
                "preflight_only": False,
            }
            environment = {"HOME": str(home), "PATH": f"{fake_bin}:{os.environ['PATH']}"}
            with mock.patch.dict(os.environ, environment, clear=False), mock.patch.object(
                plugins,
                "paper_status",
                return_value=("installed-runtime-unavailable", "test runtime unavailable"),
            ):
                first = plugins.reconcile(payload)
                self.assertTrue(first["ok"], first)
                self.assertEqual(first["marketplaces"][0]["status"], "repaired")
                self.assertEqual(first["plugins"][0]["status"], "installed-runtime-unavailable")
                action_count = len((home / "fake-codex-actions.jsonl").read_text().splitlines())
                second = plugins.reconcile(payload)
            self.assertTrue(second["ok"], second)
            self.assertEqual(second["marketplaces"][0]["status"], "match")
            self.assertEqual(action_count, len((home / "fake-codex-actions.jsonl").read_text().splitlines()))
            state = json.loads((home / "fake-codex-state.json").read_text())
            self.assertIn("target-only@local", {item["pluginId"] for item in state["installed"]})
            ownership = home / plugins.STATE_RELATIVE
            self.assertEqual(stat.S_IMODE(ownership.stat().st_mode), 0o600)
            self.assertEqual(len(list((home / ".codex").glob("config.toml.backup-plugin-*"))), 1)

    def test_legacy_plugin_state_moves_without_reading_or_merging(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            legacy = home / plugins.LEGACY_STATE_RELATIVE
            legacy.parent.mkdir(parents=True)
            legacy.write_text("{}\n", encoding="utf-8")

            state = plugins.runtime_state_path(home, migrate=True)
            self.assertEqual(state, home / plugins.STATE_RELATIVE)
            self.assertTrue(state.is_file())
            self.assertFalse((home / "Code/.ctx9").exists())
            self.assertEqual(stat.S_IMODE(state.parent.stat().st_mode), 0o700)

            legacy.parent.mkdir(parents=True)
            with self.assertRaises(plugins.PluginReconciliationError):
                plugins.runtime_state_path(home, migrate=True)

    def test_runtime_plugins_absent_from_target_marketplace_are_nonfatal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            fake_bin = root / "bin"
            marketplace = home / ".codex/.tmp/bundled-marketplaces/openai-bundled"
            (marketplace / ".agents/plugins").mkdir(parents=True)
            fake_bin.mkdir()
            fake_codex = fake_bin / "codex"
            fake_codex.write_text(FAKE_CODEX, encoding="utf-8")
            fake_codex.chmod(0o755)
            (marketplace / ".agents/plugins/marketplace.json").write_text(
                json.dumps({"name": "openai-bundled", "plugins": [{"name": "sites"}]}) + "\n",
                encoding="utf-8",
            )
            (home / ".codex/config.toml").write_text("", encoding="utf-8")
            (home / "fake-codex-state.json").write_text(
                json.dumps(
                    {
                        "marketplaces": [
                            {
                                "name": "openai-bundled",
                                "root": str(marketplace),
                                "marketplaceSource": {
                                    "sourceType": "local",
                                    "source": str(marketplace),
                                },
                            }
                        ],
                        "installed": [],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            inventory = {
                "schema_version": 1,
                "source_cli_version": "codex-cli 0.test",
                "plugins": [
                    {
                        "plugin_id": "browser@openai-bundled",
                        "name": "browser",
                        "marketplace": "openai-bundled",
                        "version": "0.1.0",
                        "enabled": True,
                        "authentication_policy": "ON_INSTALL",
                        "source_type": "runtime",
                    },
                    {
                        "plugin_id": "sites@openai-bundled",
                        "name": "sites",
                        "marketplace": "openai-bundled",
                        "version": "0.1.0",
                        "enabled": True,
                        "authentication_policy": "NONE",
                        "source_type": "runtime",
                    },
                ],
            }
            payload = {
                "home": str(home),
                "platform": "linux",
                "inventory": inventory,
                "planned_repositories": [],
                "apply": True,
                "preflight_only": False,
            }
            environment = {"HOME": str(home), "PATH": f"{fake_bin}:{os.environ['PATH']}"}
            with mock.patch.dict(os.environ, environment, clear=False):
                result = plugins.reconcile(payload)

            self.assertTrue(result["ok"], result)
            statuses = {item["plugin_id"]: item["status"] for item in result["plugins"]}
            self.assertEqual(statuses["browser@openai-bundled"], "unsupported-platform")
            self.assertEqual(statuses["sites@openai-bundled"], "installed-and-ready")
            actions = [json.loads(line) for line in (home / "fake-codex-actions.jsonl").read_text().splitlines()]
            self.assertEqual(
                [action["plugin_id"] for action in actions if action["action"] == "plugin-add"],
                ["sites@openai-bundled"],
            )


if __name__ == "__main__":
    unittest.main()
