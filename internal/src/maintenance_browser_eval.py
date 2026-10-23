"""Real browser exception -> actual Impression reporter/action/logger -> local Loki."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import re
import signal
import subprocess
import sys
import threading
import time
from urllib.request import Request, urlopen

import maintenance_runtime as runtime
from maintenance_live_eval import check, collector_module, digest, events_for, loki, run, stop



def evaluate(args):
    os.umask(0o077)
    run_id = "eval-browser-" + time.strftime("%Y%m%d-%H%M%S", time.gmtime()) + "-" + secrets.token_hex(4)
    root = args.output_root.resolve() / run_id
    root.mkdir(parents=True, mode=0o700)
    ledger = {"run_id": run_id, "owner_pid": os.getpid()}
    repo = args.impression.resolve()
    inputs = [Path(__file__), Path(__file__).with_name("maintenance_browser_bootstrap.py"), repo / "scripts/evals/k3s-triage/browser-client.tsx", repo / "scripts/evals/k3s-triage/browser-server.ts",
              repo / "scripts/evals/k3s-triage/browser-build.mjs", repo / "apps/next/src/lib/monitoring/client-error-handler.tsx",
              repo / "apps/next/src/data/errors/error-actions.ts", repo / "apps/next/src/lib/safe-action-base.ts",
              repo / "apps/next/src/lib/unauthenticated-safe-action.ts", repo / "apps/shared/src/utils/logger.ts"]
    hashes = {str(path): digest(path) for path in inputs}
    report = {"run_id": run_id, "started_ns": time.time_ns(), "real_agent_invocations": 0, "passed": False,
              "source": {"impression_sha": run(["git", "rev-parse", "HEAD"], cwd=repo), "files": hashes},
              "repair": "not_graded", "limitations": ["Eval HTTP transport replaces Next RSC wire transport", "No production telemetry or deployment", "No logical-occurrence deduplication grade"]}
    runtime.atomic_json(root / "checkpoint.json", {"phase": "setup", "report": report})
    queue = runtime.Queue(root / "queue.sqlite3")
    process = None
    try:
        run([args.node, "scripts/evals/k3s-triage/browser-build.mjs", root], cwd=repo,
            env={"PATH": "/usr/bin:/bin", "HOME": str(Path.home()), "NODE_ENV": "test", "ENVIRONMENT": "test"})
        (root / "browser-bootstrap.py").write_text(Path(__file__).with_name("maintenance_browser_bootstrap.py").read_text())
        runtime.atomic_json(root / "browser-config.json", {"browser": {"browserName": "chromium", "launchOptions": {"headless": True,
            "executablePath": "/opt/google/chrome/chrome", "args": ["--no-sandbox", "--disable-gpu"]}}})
        collector, collector_path = collector_module()
        report["source"]["collector_sha256"] = digest(collector_path)
        cli = Path.home() / ".local/lib/node_modules/@playwright/cli"
        check((cli / "playwright-cli.js").is_file(), "Approved local Playwright CLI is unavailable")
        with loki(root, run_id, ledger) as endpoint:
            config = {"test_only": True, "loki": {"test_url": endpoint, "namespace": "test", "service": "loki", "port": 3100},
                      "services": [{"namespace": run_id, "app": "impression-next", "id": "impression-next", "workspace": "impression"}]}
            start = time.time_ns()
            check(not events_for(collector, config, run_id, start, time.time_ns()), "Initial browser window was not empty")
            args_list = ["bwrap", "--die-with-parent", "--unshare-all", "--new-session", "--cap-drop", "ALL",
                "--ro-bind", "/usr", "/usr", "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
                "--symlink", "usr/bin", "/bin", "--symlink", "usr/sbin", "/sbin",
                "--ro-bind", "/etc/fonts", "/etc/fonts", "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
                "--ro-bind", str(args.node.resolve()), "/opt/node", "--ro-bind", str(cli), "/playwright-cli",
                "--ro-bind", "/opt/google/chrome", "/opt/google/chrome",
                "--ro-bind", str(root / "client.js"), "/client.js", "--ro-bind", str(root / "browser.cjs"), "/browser.cjs",
                "--ro-bind", str(root / "browser-bootstrap.py"), "/bootstrap.py", "--ro-bind", str(root / "browser-config.json"), "/browser-config.json",
                "--chdir", "/tmp", "--", "/usr/bin/python3", "/bootstrap.py"]
            env = {"PATH": "/usr/bin:/bin", "HOME": "/tmp/home", "NODE_ENV": "test", "ENVIRONMENT": "test", "K3S_EVAL_ENABLED": "1",
                   "K3S_EVAL_AUTH": secrets.token_hex(24), "K3S_EVAL_RUN_ID": run_id}
            process = subprocess.Popen(args_list, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
            ledger["browser"] = {"pid": process.pid, "session": run_id, "isolated_network": True}
            runtime.atomic_json(root / "resources.json", ledger)
            forwarding_errors = []
            def ship():
                with (root / "browser.stdout.log").open("w") as stream:
                    for line in process.stdout:
                        stream.write(line)
                        stream.flush()
                        # Only actual application logger lines are shipped, never CLI copies.
                        if not line.startswith("error:"):
                            continue
                        payload = {"streams": [{"stream": {"namespace": run_id, "app": "impression-next"}, "values": [[str(time.time_ns()), line.strip()]]}]}
                        try:
                            with urlopen(Request(endpoint + "/loki/api/v1/push", json.dumps(payload).encode(), {"Content-Type": "application/json"}), timeout=5) as response:
                                check(response.status == 204, "Loki rejected browser telemetry")
                        except Exception as error:
                            forwarding_errors.append(str(error))
            thread = threading.Thread(target=ship, daemon=True)
            thread.start()
            try:
                code = process.wait(timeout=150)
            finally:
                stop(process)
                thread.join(timeout=10)
                process.stdout.close()
                ledger["browser"].update({"exited": process.poll() is not None, "shipper_exited": not thread.is_alive(), "forwarding_errors": forwarding_errors})
                runtime.atomic_json(root / "resources.json", ledger)
            check(code == 0 and not forwarding_errors and not thread.is_alive(), "Browser operation or logging failed; inspect browser.stdout.log")
            end = time.time_ns()
            transcript = (root / "browser.stdout.log").read_text()
            check(re.search(r'"actual_action_accepted"\s*:\s*true', transcript) and '"browser_exception":' in transcript, "Browser exception/action receipt missing")
            events = events_for(collector, config, run_id, start, end)
            check(len(events) == 1 and "[CLIENT error]" in events[0]["line"] and "trim" in events[0]["line"], "Actual browser reporter event missing or duplicated")
            check(events[0]["repository"] == "impression" and events[0]["service"] == "impression-next", "Browser routing failed")
            coverage = [{"source": "loki/" + run_id, "complete": True, "cursor_ns": end}]
            queue.collect(events, end, source_cursors={coverage[0]["source"]: end}, coverage=coverage)
            pending = queue.pending()
            check(len(pending) == 1 and pending[0]["count"] == 1, "Browser grouping failed")
            queue.collect(events_for(collector, config, run_id, start, end), end + 1)
            check(queue.pending()[0]["count"] == 1, "Browser replay duplicated an occurrence")
            runtime.atomic_json(root / "telemetry.json", {"start_ns": start, "end_ns": end, "events": events, "coverage": coverage})
            report["detection"] = {"passed": True, "events": 1, "groups": 1, "routing": "passed", "replay": "passed", "real_browser_exception": True,
                "path": "ClientErrorHandler -> eval HTTP transport -> real reportClientErrorAction -> real logger -> private Loki -> actual collector/queue"}
    except BaseException as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        queue.db.close()
        if process is not None and process.poll() is None:
            stop(process)
        report["cleanup"] = {"container_removed": ledger.get("container", {}).get("removed", False), "browser_processes_exited": ledger.get("browser", {}).get("exited", False),
            "immutable_sources_unchanged": all(digest(path) == value for path, value in hashes.items())}
        report["passed"] = report.get("detection", {}).get("passed", False) and all(report["cleanup"].values()) and "error" not in report
        report["finished_ns"] = time.time_ns()
        report["runtime_seconds"] = round((report["finished_ns"] - report["started_ns"]) / 1e9, 2)
        runtime.atomic_json(root / "report.json", report)
        runtime.atomic_json(root / "checkpoint.json", {"phase": "complete", "passed": report["passed"]})
    print(json.dumps({"run_id": run_id, "passed": report["passed"], "error": report.get("error"), "report": str(root / "report.json")}), flush=True)
    return 0 if report["passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--impression", type=Path, required=True)
    parser.add_argument("--node", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    with runtime.lock(args.output_root / "browser-eval.lock"):
        return evaluate(args)


if __name__ == "__main__":
    raise SystemExit(main())
