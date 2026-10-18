from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import json
import tempfile
import unittest

SPEC = spec_from_file_location("triage", Path(__file__).with_name("triage.py"))
assert SPEC and SPEC.loader
TRIAGE = module_from_spec(SPEC)
SPEC.loader.exec_module(TRIAGE)
from maintenance_runtime import fingerprint


class TriageTests(unittest.TestCase):
    def test_redacts_protected_values_before_evidence(self) -> None:
        value = TRIAGE.redact(
            'error: request failed authorization=Bearer abc123 "api_key":"secret-value" '
            'person@example.com 08de2221-0d80-b60b-9aed-5b245f4d0000 '
            'b40852836edb9bdb32fdcdd0c312f33e'
        )
        self.assertNotIn("abc123", value)
        self.assertNotIn("secret-value", value)
        self.assertNotIn("person@example.com", value)
        self.assertIn("<redacted>", value)

    def test_fingerprint_ignores_generated_ids_and_numbers(self) -> None:
        first = fingerprint("api", "error: order 123 failed trace deadbeef1234")
        second = fingerprint("api", "error: order 999 failed trace cafeaffe5678")
        self.assertEqual(first, second)

    def test_service_is_part_of_fingerprint(self) -> None:
        self.assertNotEqual(
            fingerprint("frontend", "error: failed"),
            fingerprint("backend", "error: failed"),
        )

    def test_loki_query_telemetry_is_filtered_but_errors_remain(self) -> None:
        query = 'level=info ts=now component=querier query="error:|fatal"'
        error = 'level=error ts=now msg="request failed" err="rpc error: unavailable"'
        self.assertTrue(TRIAGE.loki_query_telemetry("monitoring/loki", query))
        self.assertFalse(TRIAGE.loki_query_telemetry("monitoring/loki", error))
        self.assertFalse(TRIAGE.loki_query_telemetry("impression-node", query))
        with tempfile.TemporaryDirectory() as temporary:
            queue = TRIAGE.Queue(Path(temporary) / "state.sqlite3")
            events = [
                {"source": "loki", "service": "monitoring/loki", "timestamp_ns": index,
                 "line": line, "repository": None}
                for index, line in enumerate([query, error], start=1)
            ]
            queue.collect(events, 3)
            self.assertEqual(TRIAGE.filter_queued_query_telemetry(queue), 1)
            self.assertEqual([item["evidence"] for item in queue.pending()], [json.dumps(events[1])])
            queue.db.close()


if __name__ == "__main__":
    unittest.main()
