from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).with_name("inspect_machine_access.py")
SPEC = importlib.util.spec_from_file_location("inspect_machine_access", SCRIPT)
assert SPEC and SPEC.loader
inspect = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inspect)


class InspectMachineAccessTests(unittest.TestCase):
    def test_wireguard_probe_parser_retains_only_numeric_evidence(self):
        self.assertEqual(
            inspect.parse_key_values(
                "peers=2 latest_handshake_epoch=1787130000 keepalive25=1 ignored=secret"
            ),
            {
                "peers": 2,
                "latest_handshake_epoch": 1787130000,
                "keepalive25": 1,
            },
        )

    def test_explicit_provider_can_be_inspected_before_switch(self):
        machine = {
            "machine_access": {
                "provider": "wireguard",
                "providers": {
                    "wireguard": {"state": "configured", "host": "10.13.13.10"},
                    "tailscale": {"state": "configured", "host": "worker.example.ts.net"},
                },
            }
        }
        self.assertEqual(
            inspect.provider_route(machine, "tailscale"),
            ("tailscale", "worker.example.ts.net"),
        )

    def test_tailscale_path_classification_uses_settled_path(self):
        output = (
            "pong from worker via DERP(jnb) in 40ms\n"
            "pong from worker via 192.0.2.10:41641 in 12ms\n"
        )
        self.assertEqual(inspect.classify_tailscale_ping(output), "direct")

    def test_peer_relay_and_derp_are_distinct(self):
        self.assertEqual(
            inspect.classify_tailscale_ping("pong via peer-relay(10.0.0.2:7777:vni:1) in 4ms"),
            "peer-relay",
        )
        self.assertEqual(
            inspect.classify_tailscale_ping("pong via DERP(jnb) in 80ms"),
            "derp",
        )


if __name__ == "__main__":
    unittest.main()
