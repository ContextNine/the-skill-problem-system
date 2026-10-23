"""Local real-telemetry and sandboxed repair eval. Never uses production queue or release authority."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import difflib
import http.client
import importlib.util
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
from urllib.request import Request, urlopen

import maintenance_runtime as runtime

PACKAGE = Path(__file__).resolve().parents[1]
IMAGE = "grafana/loki@sha256:0eaee7bf39cc83aaef46914fb58f287d4f4c4be6ec96b86c2ed55719a75e49c8"
LOKI_CONFIG = """auth_enabled: false
server:
  http_listen_port: 3100
common:
  instance_addr: 127.0.0.1
  path_prefix: /tmp/loki
  storage:
    filesystem:
      chunks_directory: /tmp/loki/chunks
      rules_directory: /tmp/loki/rules
  replication_factor: 1
  ring:
    kvstore:
      store: inmemory
schema_config:
  configs:
    - from: 2024-01-01
      store: tsdb
      object_store: filesystem
      schema: v13
      index:
        prefix: index_
        period: 24h
limits_config:
  allow_structured_metadata: false
analytics:
  reporting_enabled: false
"""


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(argv, **kwargs):
    return subprocess.run([str(arg) for arg in argv], check=True, capture_output=True, text=True, timeout=120, **kwargs).stdout.strip()


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


class VerificationFailure(RuntimeError):
    """An independent behavioral or telemetry check rejected the repair."""


def verify_check(condition, message):
    if not condition:
        raise VerificationFailure(message)


def wait_for(operation, timeout=45):
    end = time.monotonic() + timeout
    error = None
    while time.monotonic() < end:
        try:
            return operation()
        except (OSError, ValueError, http.client.HTTPException) as caught:
            error = caught
            time.sleep(0.2)
    raise RuntimeError(f"Local readiness timed out: {error}")


class UnixHTTP(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("localhost", timeout=5)
        self.path = str(path)

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.settimeout(5)
        descriptor = os.open(str(Path(self.path).parent), os.O_RDONLY | os.O_DIRECTORY)
        try:
            # Linux AF_UNIX names are limited to 108 bytes; state roots can be long.
            self.sock.connect(f"/proc/self/fd/{descriptor}/{Path(self.path).name}")
        finally:
            os.close(descriptor)


def request(path, credential, body=None, route="/scenario/backend-prompt"):
    connection = UnixHTTP(path)
    try:
        connection.request("GET" if body is None else "POST", route, None if body is None else json.dumps(body),
                           {"Authorization": "Bearer " + credential, "Content-Type": "application/json"})
        response = connection.getresponse()
        payload = response.read()
        return response.status, json.loads(payload) if payload.startswith(b"{") else payload.decode()
    finally:
        connection.close()


def stop(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
    check(process.poll() is not None, "Owned process did not exit")


@contextmanager
def loki(root, run_id, ledger):
    # Always select the explicit local socket, ignoring ambient Docker routing.
    docker = ["docker", "--host", "unix:///var/run/docker.sock"]
    check(run(docker + ["info", "--format", "{{.Name}}"]), "Local Docker unavailable")
    config = root / "loki.yaml"
    config.write_text(LOKI_CONFIG)
    config.chmod(0o644)
    name = run_id + "-loki"
    container = run(docker + ["create", "--name", name, "--label", "ctx9.eval=" + run_id,
        "--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,size=384m,uid=10001,gid=10001",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--pids-limit", "128",
        "--memory", "512m", "--cpus", "0.75", "-p", "127.0.0.1::3100",
        "--mount", f"type=bind,src={config},dst=/etc/eval-loki.yaml,readonly",
        IMAGE, "-config.file=/etc/eval-loki.yaml"])
    ledger["container"] = {"id": container, "name": name, "image": IMAGE, "local_socket": True}
    runtime.atomic_json(root / "resources.json", ledger)
    try:
        run(docker + ["start", container])
        address = run(docker + ["port", container, "3100/tcp"])
        check(address.startswith("127.0.0.1:"), "Loki must bind loopback only")
        endpoint = "http://" + address
        wait_for(lambda: urlopen(endpoint + "/ready", timeout=2).close(), timeout=60)
        yield endpoint
    finally:
        info = json.loads(run(docker + ["inspect", container]))[0]
        check(info["Config"]["Labels"].get("ctx9.eval") == run_id, "Container ownership mismatch")
        (root / "loki.log").write_text(run(docker + ["logs", container]))
        run(docker + ["rm", "-f", container])
        absent = subprocess.run(docker + ["inspect", container], capture_output=True).returncode != 0
        ledger["container"]["removed"] = absent
        runtime.atomic_json(root / "resources.json", ledger)
        check(absent, "Owned Loki was not removed")


def build(repo, node, overlay, output):
    clean_env = {"PATH": "/usr/bin:/bin", "HOME": str(Path.home()), "NODE_ENV": "test", "ENVIRONMENT": "test"}
    result = subprocess.run([str(node), "scripts/evals/k3s-triage/build.mjs", str(overlay), str(output)],
                            cwd=repo, env=clean_env, text=True, capture_output=True, timeout=120)
    (output.with_suffix(".build.log")).write_text(result.stdout + result.stderr)
    check(result.returncode == 0, f"Test build failed; see {output.with_suffix('.build.log')}")
    return runtime.load(str(output) + ".manifest.json")


@contextmanager
def application(root, node, artifact, run_id, endpoint, ledger, label, *, app_label="impression-node"):
    runtime_dir = root / (label + "-socket")
    runtime_dir.mkdir(mode=0o700)
    credential = secrets.token_hex(24)
    entrypoint = "/app.mjs" if artifact.suffix == ".mjs" else "/app.cjs"
    args = ["bwrap", "--die-with-parent", "--unshare-all", "--new-session", "--cap-drop", "ALL",
            "--ro-bind", "/usr", "/usr", "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
            "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
            "--ro-bind", str(node), "/opt/node", "--ro-bind", str(artifact), entrypoint,
            "--bind", str(runtime_dir), "/trial", "--", "/opt/node", entrypoint]
    env = {"PATH": "/usr/bin:/bin", "NODE_ENV": "test", "ENVIRONMENT": "test", "K3S_EVAL_ENABLED": "1",
           "K3S_EVAL_RUN_ID": run_id, "K3S_EVAL_AUTH": credential, "K3S_EVAL_SOCKET": "/trial/app.sock"}
    process = subprocess.Popen(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, start_new_session=True)
    errors = []
    lines = []
    def ship():
        with (root / (label + ".stdout.log")).open("w") as transcript:
            for line in process.stdout:
                transcript.write(line)
                transcript.flush()
                text = line.rstrip()
                if not text:
                    continue
                lines.append(text)
                payload = {"streams": [{"stream": {"namespace": run_id, "app": app_label},
                    "values": [[str(time.time_ns()), text]]}]}
                try:
                    with urlopen(Request(endpoint + "/loki/api/v1/push", json.dumps(payload).encode(),
                                         {"Content-Type": "application/json"}), timeout=5) as response:
                        check(response.status == 204, "Loki rejected actual application stdout")
                except Exception as error:
                    errors.append(str(error))
    thread = threading.Thread(target=ship, daemon=True)
    thread.start()
    resource = {"pid": process.pid, "label": label, "artifact_sha256": digest(artifact)}
    ledger.setdefault("applications", []).append(resource)
    runtime.atomic_json(root / "resources.json", ledger)
    try:
        status, identity = wait_for(lambda: request(runtime_dir / "app.sock", credential, route="/identity"))
        check(status == 200 and identity["runId"] == run_id, "Incorrect test deployment identity")
        check(request(runtime_dir / "app.sock", "invalid", route="/identity")[0] == 401, "Scenario auth not enforced")
        yield lambda body, route="/scenario/backend-prompt": request(runtime_dir / "app.sock", credential, body, route), identity
    finally:
        stop(process)
        thread.join(timeout=10)
        process.stdout.close()
        for owned_socket in runtime_dir.glob("*.sock"):
            if owned_socket.is_socket():
                owned_socket.unlink()
        resource.update({"exited": process.poll() is not None, "socket_removed": not (runtime_dir / "app.sock").exists(),
                         "shipper_exited": not thread.is_alive(), "shipper_errors": errors, "stdout_lines": len(lines)})
        runtime.atomic_json(root / "resources.json", ledger)
        check(not errors and not thread.is_alive(), "Application telemetry forwarding failed")


def collector_module():
    candidates = (
        PACKAGE.parent / "edit/skills/areas/infrastructure/k3s-triage-and-hotfix/scripts/triage.py",
        PACKAGE.parent / "skills/k3s-triage-and-hotfix/scripts/triage.py",
    )
    path = next((candidate for candidate in candidates if candidate.is_file()), None)
    check(path is not None, "The triage collector is missing from this Fleet source or installation")
    spec = importlib.util.spec_from_file_location("live_eval_triage", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, path


def events_for(collector, config, run_id, start, end):
    return collector.loki_events(config, run_id, start, end)


def verify_result(call, identity, scenario, overlay_hash):
    verify_check(identity["environment"] == "test" and identity["source"] == overlay_hash, "Local deployment source mismatch")
    status, body = call(scenario["request"])
    verify_check(status == 200 and body["result"] == scenario["expected_result"], f"Original operation not repaired: {status} {body}")
    for probe in scenario["additional_probes"]:
        status, body = call({**scenario["request"], "input": probe["input"]})
        verify_check(status == 200 and body["result"] == probe["expected"], "Additional behavior probe failed")
    verify_check(call({"invalid": True})[0] == 400, "Input checks weakened")
    return {"original_operation": "passed", "additional_behavior_probes": len(scenario["additional_probes"]),
            "input_validation": "passed", "deployment_identity": identity}


def trial(args, root, index):
    root.mkdir(mode=0o700)
    run_id = root.name
    scenario_path = PACKAGE / "defaults/maintenance-eval/backend.json"
    scenario = runtime.load(scenario_path)
    check(scenario["schema_version"] == 1, "Unknown scenario version")
    repo = args.impression.resolve()
    original = repo / scenario["source"]
    source_before = original.read_text()
    immutable = [scenario_path, Path(__file__), PACKAGE / "src/maintenance_eval_sandbox.py",
                 repo / "scripts/evals/k3s-triage/server.ts", repo / "scripts/evals/k3s-triage/build.mjs",
                 repo / "apps/node/src/middleware/server-error.middleware.ts", repo / "apps/shared/src/utils/logger.ts"]
    hashes = {str(path): digest(path) for path in immutable}
    report = {"run_id": run_id, "trial": index, "started_ns": time.time_ns(), "mode": args.mode,
              "source": {"impression_sha": run(["git", "rev-parse", "HEAD"], cwd=repo), "original_sha256": digest(original),
                         "source_path": scenario["source"], "definition_sha256": digest(scenario_path), "immutable_files": hashes},
              "real_agent_invocations": 0, "detection": {"passed": False}, "repair": {"passed": False, "status": "not_run"},
              "excluded_grades": ["Browser client reporter", "Native Langfuse", "Kubernetes inventory", "Second service", "Cross-source logical-occurrence deduplication", "Production release and rollback"]}
    ledger = {"run_id": run_id, "owner_pid": os.getpid(), "started_ns": time.time_ns()}
    runtime.atomic_json(root / "checkpoint.json", {"phase": "setup", "report": report})
    overlay_dir = root / "overlay"
    overlay_dir.mkdir()
    overlay = overlay_dir / original.name
    check(source_before.count(scenario["seed"]["before"]) == 1, "Seed precondition changed; refusing to patch")
    overlay.write_text(source_before.replace(scenario["seed"]["before"], scenario["seed"]["after"]))
    report["source"]["seeded_sha256"] = digest(overlay)
    (root / "seed.patch").write_text("".join(difflib.unified_diff(source_before.splitlines(True), overlay.read_text().splitlines(True), fromfile=scenario["source"], tofile="overlay/" + original.name)))
    queue = runtime.Queue(root / "queue.sqlite3")
    collector, collector_path = collector_module()
    report["source"]["collector_sha256"] = digest(collector_path)
    node = args.node.resolve()
    try:
        artifact = root / "before.cjs"
        report["before_build"] = build(repo, node, overlay, artifact)
        with loki(root, run_id, ledger) as endpoint:
            config = {"test_only": True, "loki": {"test_url": endpoint, "namespace": "test", "service": "loki", "port": 3100, "limit_per_service": 1000},
                      "services": [{"namespace": run_id, "app": "impression-node", "id": scenario["service"], "workspace": "impression"}]}
            start = time.time_ns()
            with application(root, node, artifact, run_id, endpoint, ledger, "before") as (call, identity):
                # Initial empty window goes through actual Loki and the actual queue.
                empty_end = time.time_ns()
                empty = events_for(collector, config, run_id, start, empty_end)
                check(not empty, "Expected no error before the operation")
                queue.collect(empty, empty_end)
                check(not queue.pending(), "Empty window created an investigation")
                no_error_root = root / "empty-dispatch"
                runtime.atomic_json(no_error_root / "skills/config/k3s-maintenance/config.json", {"agent": {"provider": "external", "command": [sys.executable, "-c", "raise RuntimeError('Unexpected empty-window agent invocation')"]}, "issues": {"provider": "off"}})
                previous_config = os.environ.get("CTX9_AUTOMATION_CONFIG_ROOT")
                os.environ["CTX9_AUTOMATION_CONFIG_ROOT"] = str(no_error_root)
                try:
                    with runtime.lock(root / "empty-dispatch.lock") as fd:
                        runtime.investigate(queue, {}, root, "empty-window", [], fd)
                finally:
                    if previous_config is None:
                        os.environ.pop("CTX9_AUTOMATION_CONFIG_ROOT", None)
                    else:
                        os.environ["CTX9_AUTOMATION_CONFIG_ROOT"] = previous_config
                check(not (root / "runs/empty-window").exists(), "Empty window invoked the agent adapter")
                runtime.atomic_json(root / "no-error.json", {"events": empty, "pending": 0, "real_agent_invocations": 0, "checkpoint_ns": empty_end})
                status, body = call(scenario["request"])
                report["initial_operation"] = {"status": status, "body": body, "identity": identity}
                check(status == 500 and body.get("name") == "TypeError", "Seeded operation did not fail through the real error middleware")
            end = time.time_ns()
            events = events_for(collector, config, run_id, start, end)
            check(events and all(event["service"] == scenario["service"] and event["repository"] == "impression" for event in events), "Actual telemetry missing or routed incorrectly")
            check(any("trim" in event["line"] and "TypeError" in event["line"] for event in events), "Seed failure did not reach Loki")
            coverage = [{"source": "loki/" + run_id, "complete": True, "cursor_ns": end}]
            queue.collect(events, end, coverage=coverage, source_cursors={coverage[0]["source"]: end})
            pending = queue.pending()
            check(len(pending) == 1, "Expected exactly one backend incident group")
            count = pending[0]["count"]
            queue.collect(events_for(collector, config, run_id, start, end), end + 1)
            check(len(queue.pending()) == 1 and queue.pending()[0]["count"] == count, "Replay changed queue occurrences")
            runtime.atomic_json(root / "telemetry.json", {"start_ns": start, "end_ns": end, "events": events, "coverage": coverage})
            report["detection"] = {"passed": True, "source": "actual app middleware/logger stdout -> isolated Loki -> actual collector/queue",
                "events": len(events), "groups": len(pending), "replay": "passed", "routing": "passed", "no_error_agent_invocations": 0,
                "coverage_scope": ["run-owned Loki only"], "all_configured_sources_complete": True}
            runtime.atomic_json(root / "checkpoint.json", {"phase": "detected", "report": report})
            if args.mode != "detect":
                evidence = root / "evidence.json"
                runtime.atomic_json(evidence, {"run_id": run_id, "coverage": coverage, "incidents": [{**row, "evidence": json.loads(row["evidence"])} for row in pending],
                    "eval": {"repository": "impression", "initial_sha": report["source"]["impression_sha"], "source": "/repair/ai-run-prompt.ts",
                             "observed_request": scenario["request"], "initial_operation": report["initial_operation"]}})
                schema = PACKAGE / "schemas/maintenance-outcome.schema.json"
                sandbox = PACKAGE / "src/maintenance_eval_sandbox.py"
                command = [sys.executable, str(sandbox), "--trial", str(root), "--vault", str(args.vault.resolve()),
                    "--skills", str(args.skills.resolve()), "--evidence", str(evidence), "--schema", str(schema),
                    "--output", "{output}", "--prompt", "{prompt}", "--model", args.model]
                if args.mode == "preflight":
                    command = [str(root / "preflight-outcome.json") if value == "{output}" else "sandbox preflight" if value == "{prompt}" else value for value in command]
                    preflight = json.loads(run(command + ["--preflight-only"]))
                    runtime.atomic_json(root / "sandbox-preflight.json", preflight)
                    report["sandbox_preflight"] = preflight
                else:
                    settings = root / "config/skills/config/k3s-maintenance/config.json"
                    runtime.atomic_json(settings, {"agent": {"provider": "external", "command": command, "timeout_seconds": 660}, "issues": {"provider": "off"}})
                    prior = os.environ.get("CTX9_AUTOMATION_CONFIG_ROOT")
                    os.environ["CTX9_AUTOMATION_CONFIG_ROOT"] = str(root / "config")
                    agent_start = time.monotonic()
                    try:
                        with runtime.lock(root / "eval-mutation.lock") as fd:
                            outcome = runtime.run_agent(cwd=args.vault.resolve(), skill="k3s-triage-and-hotfix", evidence=evidence,
                                                        output_dir=root / "agent-run", schema=schema, lock_fd=fd)
                        validated = runtime.investigation_outcomes(outcome, pending)
                        runtime.atomic_json(root / "validated-outcomes.json", validated)
                    finally:
                        if prior is None:
                            os.environ.pop("CTX9_AUTOMATION_CONFIG_ROOT", None)
                        else:
                            os.environ["CTX9_AUTOMATION_CONFIG_ROOT"] = prior
                        report["agent_runtime_seconds"] = round(time.monotonic() - agent_start, 2)
                        trajectory = root / "agent-run/agent.events.jsonl"
                        if trajectory.exists():
                            report["real_agent_invocations"] = sum(line.strip() == '{"real_agent_launch": true}' for line in trajectory.read_text().splitlines())
                            turns = []
                            for line in trajectory.read_text().splitlines():
                                try:
                                    event = json.loads(line)
                                    if event.get("type") == "turn.completed":
                                        turns.append(event.get("usage", {}))
                                except ValueError:
                                    pass
                            report["agent_usage"] = turns
                    check(overlay.is_file() and not overlay.is_symlink() and digest(overlay) != report["source"]["seeded_sha256"], "No regular repaired source overlay")
                    check(list(overlay_dir.iterdir()) == [overlay], "Repair changed unrelated overlay files")
                    repaired = root / "after.cjs"
                    report["after_build"] = build(repo, node, overlay, repaired)
                    verification_start = time.time_ns()
                    with application(root, node, repaired, run_id, endpoint, ledger, "after") as (call, identity):
                        verification = verify_result(call, identity, scenario, digest(overlay))
                        verification_end = time.time_ns()
                        check(not events_for(collector, config, run_id, verification_start, verification_end), "Repair still emits runtime errors")
                        control_start = time.time_ns()
                        control_status, _ = call({}, "/scenario/telemetry-control")
                        check(control_status == 500, "Immutable telemetry control did not fail")
                    control_end = time.time_ns()
                    control_events = events_for(collector, config, run_id, control_start, control_end)
                    verify_check(any("eval-telemetry-integrity" in event["line"] for event in control_events), "Repair silenced the real logger")
                    runtime.atomic_json(root / "telemetry-control.json", {"start_ns": control_start, "end_ns": control_end, "events": control_events})
                    check(len(events_for(collector, config, run_id, start, end)) == len(events), "Original error telemetry was suppressed")
                    report["repair"] = {"passed": True, "status": "independently_verified", "verification": verification,
                        "release_adapter": "local immutable bundle redeployment", "artifact_sha256": digest(repaired), "telemetry_preserved": True}
    except BaseException as error:
        report["error"] = f"{type(error).__name__}: {error}"
        if args.mode == "repair" and (report["real_agent_invocations"] or "after_build" in report):
            report["repair"] = {"passed": False, "status": "failed", "failure": str(error), "failure_kind": type(error).__name__}
    finally:
        queue.db.close()
        unchanged = digest(original) == report["source"]["original_sha256"]
        immutable_ok = all(digest(path) == value for path, value in hashes.items())
        report["cleanup"] = {"original_source_unchanged": unchanged, "verifier_and_telemetry_unchanged": immutable_ok,
            "container_removed": ledger.get("container", {}).get("removed", False),
            "all_application_processes_exited": all(item.get("exited") and item.get("socket_removed") and item.get("shipper_exited") for item in ledger.get("applications", [])),
            "retained": "private source overlays, bundles, evidence, queue and agent trajectory; no live resources"}
        report["finished_ns"] = time.time_ns()
        report["runtime_seconds"] = round((report["finished_ns"] - report["started_ns"]) / 1e9, 2)
        report["passed"] = report["detection"]["passed"] and all(value for key, value in report["cleanup"].items() if key != "retained") and (args.mode != "repair" or report["repair"]["passed"]) and "error" not in report
        runtime.atomic_json(root / "report.json", report)
        runtime.atomic_json(root / "checkpoint.json", {"phase": "complete", "passed": report["passed"], "report": str(root / "report.json")})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--impression", type=Path, required=True)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--skills", type=Path, required=True)
    parser.add_argument("--node", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--mode", choices=["detect", "preflight", "repair"], default="detect")
    parser.add_argument("--trials", type=int, choices=range(1, 6), default=1)
    parser.add_argument("--model", default="gpt-6.1-sol")
    args = parser.parse_args()
    os.umask(0o077)
    access = json.loads(run(["vault", "access", "status"]))
    check(access.get("ok") is True, "Registered Vault access is unavailable")
    args.output_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    # One owned lock, unrelated to installed maintenance queues and timers.
    reports = []
    def interrupted(_number, _frame):
        raise KeyboardInterrupt("Owned eval received termination")
    signal.signal(signal.SIGTERM, interrupted)
    with runtime.lock(args.output_root / "eval.lock"):
        for index in range(args.trials):
            run_id = "eval-" + time.strftime("%Y%m%d-%H%M%S", time.gmtime()) + "-" + secrets.token_hex(4)
            report = trial(args, args.output_root / run_id, index + 1)
            reports.append(report)
            print(json.dumps({"run_id": run_id, "passed": report["passed"], "detection": report["detection"], "repair": report["repair"], "error": report.get("error")}), flush=True)
            if not report["passed"]:
                break
    summary = {"mode": args.mode, "passed": all(row["passed"] for row in reports), "trials": len(reports),
        "real_agent_invocations": sum(row["real_agent_invocations"] for row in reports),
        "detection_passes": sum(row["detection"]["passed"] for row in reports), "repair_passes": sum(row["repair"]["passed"] for row in reports),
        "reports": [str(args.output_root / row["run_id"] / "report.json") for row in reports]}
    runtime.atomic_json(args.output_root / "latest.json", summary)
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
