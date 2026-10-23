"""Offline queue/dispatch eval. This is not a real telemetry or repair trial."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import time
from unittest.mock import patch

import maintenance_runtime as runtime


def evaluate(suite_path, output):
    suite = runtime.load(suite_path)
    if suite["schema_version"] != 1 or suite["suite"] != "deterministic-replay":
        raise ValueError("Only the offline deterministic replay suite is supported")
    results = []
    for case in suite["cases"]:
        with tempfile.TemporaryDirectory(prefix="maintenance-eval-") as temporary:
            root = Path(temporary)
            queue = runtime.Queue(root / "queue.sqlite3")
            dispatches = []
            def agent(**kwargs):
                evidence = runtime.load(kwargs["evidence"])
                dispatches.append(evidence)
                return {"incidents": [
                    {"incident_id": row["id"], "status": "unresolved",
                     "summary": "Offline dispatch stub, no repair attempted", "next_action": "Not applicable",
                     "repositories": [], "verification": []} for row in evidence["incidents"]]}
            try:
                events = runtime.redact(case["events"])
                now = time.time_ns()
                events = [{**event,"timestamp_ns":now + index} for index,event in enumerate(events)]
                queue.collect(events, now)
                initial = queue.pending()
                # Replaying a source window must not increment occurrences or dispatch twice.
                queue.collect(events, now+1)
                replay = queue.pending()
                with runtime.lock(root / "mutation.lock") as fd, patch.object(runtime, "maintenance_settings", return_value={"agent":{"provider":"codex"}}), patch.object(runtime, "investigation_root", return_value=root), patch.object(runtime, "run_agent", side_effect=agent):
                    runtime.investigate(queue, {}, root, case["id"], [], fd)
                    runtime.investigate(queue, {}, root, case["id"] + "-replay", [], fd)
                actual = {"groups": queue.db.execute("SELECT count(*) FROM incidents").fetchone()[0], "agent_dispatches": len(dispatches),
                          "correlated_groups": sum(bool(row["correlated_incidents"]) for row in initial)}
                failures = [f"{key}: expected {value}, got {actual.get(key)}" for key, value in case["expected"].items() if actual.get(key) != value]
                if [(row["id"], row["count"]) for row in initial] != [(row["id"], row["count"]) for row in replay]:
                    failures.append("Replayed events changed group identity or occurrence count")
                if queue.db.execute("SELECT value FROM metadata WHERE key='cursor_ns'").fetchone()[0] != str(now+1):
                    failures.append("Checkpoint did not advance")
                result = {"id": case["id"], "passed": not failures, "actual": actual, "failures": failures}
            except Exception as error:
                result = {"id": case["id"], "passed": False, "failures": [runtime.redact(str(error))]}
            finally:
                queue.db.close()
            results.append(result)
    report = {
        "schema_version": 1, "suite": suite["suite"],
        "definition_sha256": hashlib.sha256(Path(suite_path).read_bytes()).hexdigest(),
        "created_ns": time.time_ns(), "passed": all(row["passed"] for row in results),
        "real_codex_invocations": 0, "agent": "offline dispatch stub",
        "limitations": ["No real browser/server/Langfuse telemetry", "No agent repair or deployment",
                        "No cross-source logical-occurrence deduplication grade"],
        "cases": results,
    }
    runtime.atomic_json(output, report)
    print(json.dumps({"passed": report["passed"], "cases": len(results), "report": str(output), "real_codex_invocations": 0}))
    return 0 if report["passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    suite = Path(__file__).resolve().parents[1] / "defaults/maintenance-eval/replay.json"
    return evaluate(suite, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
