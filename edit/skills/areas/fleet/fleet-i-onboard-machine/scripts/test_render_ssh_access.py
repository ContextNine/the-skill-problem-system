from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).with_name("render_ssh_access.py")
SPEC = importlib.util.spec_from_file_location("render_ssh_access", SCRIPT)
assert SPEC and SPEC.loader
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)


class RenderSshAccessTests(unittest.TestCase):
    def registry(self):
        return {
            "schema_version": 7,
            "primary_machine_id": "primary",
            "machines": [
                {
                    "id": "primary",
                    "enabled": True,
                    "platform": "macos",
                    "transport": "local",
                    "ssh_alias": "primary",
                    "fleet_shell": {"identity_file": "~/.ssh/primary_fleet_ed25519"},
                    "machine_access": {
                        "provider": "wireguard",
                        "ssh_user": "matt",
                        "providers": {
                            "wireguard": {
                                "state": "configured",
                                "host": "10.13.13.2",
                            }
                        },
                    },
                },
                {
                    "id": "worker",
                    "enabled": True,
                    "platform": "macos",
                    "transport": "ssh",
                    "ssh_alias": "worker",
                    "fleet_shell": {"identity_file": "~/.ssh/worker_fleet_ed25519"},
                    "machine_access": {
                        "provider": "tailscale",
                        "ssh_user": "matt",
                        "identity_file": "~/.ssh/fleet_ed25519",
                        "lan_host": "worker.local",
                        "providers": {
                            "wireguard": {
                                "state": "configured",
                                "host": "10.13.13.10",
                            },
                            "tailscale": {
                                "state": "configured",
                                "host": "worker.example.ts.net",
                            },
                        },
                    },
                },
            ],
        }

    def test_selected_provider_renders_stable_and_diagnostic_aliases(self):
        with mock.patch.object(renderer.platform, "system", return_value="Darwin"):
            rendered = renderer.render_registry(self.registry())
        self.assertIn("Host worker worker-mesh worker-lan", rendered)
        self.assertIn("Host worker-mesh\n    HostName worker.example.ts.net", rendered)
        self.assertIn("Match originalhost worker", rendered)
        self.assertIn("BatchMode yes", rendered)
        self.assertIn("PasswordAuthentication no", rendered)
        self.assertIn("StrictHostKeyChecking yes", rendered)
        self.assertNotIn("worker-wg", rendered)
        self.assertNotIn("10.13.13.10", rendered)

    def test_worker_source_renders_primary_selected_provider_with_source_identity(self):
        rendered = renderer.render_registry(self.registry(), source_machine_id="worker")
        self.assertIn("Host primary primary-mesh", rendered)
        self.assertIn("HostName 10.13.13.2", rendered)
        self.assertIn("IdentityFile ~/.ssh/worker_fleet_ed25519", rendered)
        self.assertIn("UseKeychain yes", rendered)
        self.assertIn("AddKeysToAgent yes", rendered)
        self.assertNotIn("Host worker", rendered)

    def test_linux_source_does_not_render_macos_keychain_options(self):
        registry = self.registry()
        registry["machines"][1]["platform"] = "linux"
        rendered = renderer.render_registry(registry, source_machine_id="worker")
        self.assertNotIn("UseKeychain", rendered)
        self.assertNotIn("AddKeysToAgent", rendered)

    def test_load_registry_rejects_an_outdated_schema(self):
        with tempfile.TemporaryDirectory() as temporary:
            registry_path = Path(temporary) / "machines.json"
            registry = self.registry()
            registry["schema_version"] = 5
            registry_path.write_text(json.dumps(registry), encoding="utf-8")
            with self.assertRaisesRegex(renderer.RenderError, "must be 7"):
                renderer.load_registry(registry_path)

    def test_pending_selected_provider_is_not_rendered(self):
        registry = self.registry()
        registry["machines"][1]["machine_access"]["providers"]["tailscale"] = {
            "state": "pending"
        }
        self.assertNotIn("Host worker", renderer.render_registry(registry))

    def test_apply_preserves_unrelated_config_and_writes_include_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            registry_path = root / "machines.json"
            ssh_config = root / ".ssh/config"
            output = root / ".ssh/config.d/vault-machine-access.conf"
            registry_path.write_text(json.dumps(self.registry()), encoding="utf-8")
            ssh_config.parent.mkdir(parents=True)
            ssh_config.write_text("Host github.com\n    User git\n", encoding="utf-8")
            renderer.apply_render(
                registry_path=registry_path,
                ssh_config=ssh_config,
                output=output,
                apply=True,
            )
            renderer.apply_render(
                registry_path=registry_path,
                ssh_config=ssh_config,
                output=output,
                apply=True,
            )
            config = ssh_config.read_text(encoding="utf-8")
            self.assertEqual(config.count(renderer.INCLUDE_LINE), 1)
            self.assertIn("Host github.com", config)
            self.assertIn("worker.example.ts.net", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
