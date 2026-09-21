from __future__ import annotations

import importlib.util
from pathlib import Path
import plistlib
import unittest


SCRIPT = Path(__file__).with_name("manage_worker_mac_sleep_service.py")
SPEC = importlib.util.spec_from_file_location("manage_worker_mac_sleep_service", SCRIPT)
assert SPEC and SPEC.loader
service = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(service)


class ManageWorkerMacSleepServiceTests(unittest.TestCase):
    def test_plist_owns_exact_persistent_system_sleep_assertion(self):
        value = plistlib.loads(service.plist_bytes())
        self.assertEqual(value["Label"], "com.ctx9.worker.prevent-system-sleep")
        self.assertEqual(value["ProgramArguments"], ["/usr/bin/caffeinate", "-s"])
        self.assertTrue(value["RunAtLoad"])
        self.assertTrue(value["KeepAlive"])


if __name__ == "__main__":
    unittest.main()
