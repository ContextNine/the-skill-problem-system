"""Isolated real Langfuse observation acceptance, without managed credentials or model calls."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import ipaddress
import os
from pathlib import Path
import secrets
import signal
import subprocess
import time
from urllib.request import urlopen

import maintenance_runtime as runtime
from maintenance_live_eval import PACKAGE, check, digest, run, wait_for as wait_base

DOCKER = ["docker", "--host", "unix:///var/run/docker.sock"]
IMAGES = {
    "web": "langfuse/langfuse@sha256:35461119756177199bf4412ceed03e0f637ca5c4a6b8b85d9e31c35e515e670d",
    "worker": "langfuse/langfuse-worker@sha256:080377807b6d1fca2117662840161e60a0ab6842b2578ef39ea17df80ba42bfd",
    "postgres": "postgres@sha256:eee6c6e1b0894fa4fe0075eb054af9fd1cf39a35321c2d4110626cfe506411fb",
    "clickhouse": "clickhouse/clickhouse-server@sha256:0152dd511befe6a2c2ef53e930726179669b08116da78500b37c51c96ff5ee77",
    "minio": "cgr.dev/chainguard/minio@sha256:d88920d6a50bd0b088223b688be3b76c63e6205dbe494437f67ba1240ea12880",
    "redis": "redis@sha256:02f2cc4882f8bf87c79a220ac958f58c700bdec0dfb9b9ea61b62fb0e8f1bfcf",
    "producer": "node@sha256:6c74791e557ce11fc957704f6d4fe134a7bc8d6f5ca4403205b2966bd488f6b3",
}


def wait_for(operation, timeout):
    def ready():
        try:
            return operation()
        except subprocess.SubprocessError as error:
            raise ValueError(str(error)) from error
    return wait_base(ready, timeout=timeout)


class LocalTarget:
    def __init__(self, root, run_id):
        self.root, self.run_id = root, run_id
        self.network = run_id + "-network"
        self.ledger = {"run_id": run_id, "owner_pid": os.getpid(), "containers": [], "network": {"name": self.network}}
        self.protected = []

    def save(self):
        runtime.atomic_json(self.root / "resources.json", self.ledger)

    def redact(self, value):
        for secret in self.protected:
            value = value.replace(secret, "<synthetic-redacted>")
        return value

    def start_network(self):
        self.ledger["network"]["id"] = run(DOCKER + ["network", "create", "--internal", "--label", "ctx9.eval=" + self.run_id, self.network])
        self.save()

    def create(self, role, env, *, options=(), command=(), entrypoint=None, memory="512m", cpus="1"):
        args = DOCKER + ["create", "--name", self.run_id + "-" + role, "--label", "ctx9.eval=" + self.run_id,
            "--network", self.network, "--network-alias", "lf-" + role, "--security-opt", "no-new-privileges",
            "--memory", memory, "--cpus", cpus, "--pids-limit", "1024"]
        for name in env:
            args += ["--env", name]
        args += list(options)
        if entrypoint:
            args += ["--entrypoint", entrypoint]
        args += [IMAGES[role]] + list(command)
        identity = run(args, env={"PATH": "/usr/bin:/bin", **env})
        image_id = run(DOCKER + ["inspect", "--format", "{{.Image}}", identity])
        self.ledger["containers"].append({"role": role, "id": identity, "image": IMAGES[role], "image_id": image_id})
        self.save()
        run(DOCKER + ["start", identity])
        return identity

    def cleanup(self):
        failures = []
        for item in reversed(self.ledger["containers"]):
            try:
                label = run(DOCKER + ["inspect", "--format", '{{index .Config.Labels "ctx9.eval"}}', item["id"]])
                check(label == self.run_id, "Native container ownership mismatch")
                logs = subprocess.run(DOCKER + ["logs", "--tail", "200", item["id"]], text=True, capture_output=True, timeout=10)
                (self.root / (item["role"] + ".log")).write_text(self.redact(logs.stdout + logs.stderr))
                # Only anonymous volumes attached to this exact owned container can be removed.
                volumes = json.loads(run(DOCKER + ["inspect", "--format", "{{json .Mounts}}", item["id"]]))
                names = [mount["Name"] for mount in volumes if mount["Type"] == "volume"]
                run(DOCKER + ["rm", "-fv", item["id"]])
                item["removed"] = subprocess.run(DOCKER + ["inspect", item["id"]], capture_output=True).returncode != 0
                item["anonymous_volumes_removed"] = all(subprocess.run(DOCKER + ["volume", "inspect", name], capture_output=True).returncode != 0 for name in names)
            except Exception as error:
                failures.append(self.redact(str(error)))
            self.save()
        if self.ledger["network"].get("id"):
            try:
                label = run(DOCKER + ["network", "inspect", "--format", '{{index .Labels "ctx9.eval"}}', self.network])
                check(label == self.run_id, "Native network ownership mismatch")
                run(DOCKER + ["network", "rm", self.network])
                self.ledger["network"]["removed"] = subprocess.run(DOCKER + ["network", "inspect", self.network], capture_output=True).returncode != 0
            except Exception as error:
                failures.append(self.redact(str(error)))
        self.ledger["cleanup_failures"] = failures
        self.save()
        return not failures and self.ledger["network"].get("removed", False) and all(row.get("removed") and row.get("anonymous_volumes_removed") for row in self.ledger["containers"])


def evaluate(args):
    os.umask(0o077)
    run_id = "eval-native-" + time.strftime("%Y%m%d-%H%M%S", time.gmtime()) + "-" + secrets.token_hex(4)
    root = args.output_root.resolve() / run_id
    root.mkdir(mode=0o700)
    target = LocalTarget(root, run_id)
    report = {"run_id": run_id, "started_ns": time.time_ns(), "real_agent_invocations": 0, "paid_model_calls": 0,
        "passed": False, "repair": "not_graded", "limitations": ["Synthetic project only; production native custody is unchanged", "No cross-source logical-occurrence deduplication grade"]}
    repo = args.impression.resolve()
    source = repo / "apps/node/src/services/ai-runs/ai-run-prompt.ts"
    before = source.read_text()
    hashes = {str(path): digest(path) for path in [source, Path(__file__), repo / "scripts/evals/k3s-triage/trace.ts",
        repo / "scripts/evals/k3s-triage/trace-build.mjs", repo / "apps/node/src/ai-observability/ai-trace.ts",
        PACKAGE / "src/ai_quality/runtime-errors.ts", PACKAGE / "src/ai_quality/langfuse-v1-client.ts"]}
    report["source"] = {"impression_sha": run(["git", "rev-parse", "HEAD"], cwd=repo), "files": hashes}
    runtime.atomic_json(root / "checkpoint.json", {"phase": "setup", "report": report})
    queue = runtime.Queue(root / "queue.sqlite3")
    try:
        scenario = runtime.load(PACKAGE / "defaults/maintenance-eval/backend.json")
        check(before.count(scenario["seed"]["before"]) == 1, "Seed source changed")
        overlay = root / "ai-run-prompt.ts"
        overlay.write_text(before.replace(scenario["seed"]["before"], scenario["seed"]["after"]))
        runtime.atomic_json(root / "request.json", scenario["request"])
        run([args.node, "scripts/evals/k3s-triage/trace-build.mjs", overlay, root / "trace.mjs"], cwd=repo,
            env={"PATH": "/usr/bin:/bin", "HOME": str(Path.home()), "NODE_ENV": "test", "ENVIRONMENT": "test"})
        passwords = {name: secrets.token_hex(24) for name in ["postgres", "clickhouse", "minio", "salt", "nextauth", "user"]}
        public_key, secret_key = "pk-lf-" + secrets.token_hex(16), "sk-lf-" + secrets.token_hex(24)
        encryption_key = secrets.token_hex(32)
        target.protected = [*passwords.values(), public_key, secret_key, encryption_key]
        target.start_network()
        postgres = target.create("postgres", {"POSTGRES_USER": "eval", "POSTGRES_PASSWORD": passwords["postgres"], "POSTGRES_DB": "eval"},
            options=["--tmpfs", "/var/lib/postgresql/data:rw,size=384m"], memory="512m")
        wait_for(lambda: run(DOCKER + ["exec", postgres, "pg_isready", "-U", "eval"]), timeout=45)
        clickhouse = target.create("clickhouse", {"CLICKHOUSE_USER": "eval", "CLICKHOUSE_PASSWORD": passwords["clickhouse"], "CLICKHOUSE_DB": "default"},
            options=["--tmpfs", "/var/lib/clickhouse:rw,size=512m"], memory="2g")
        wait_for(lambda: run(DOCKER + ["exec", clickhouse, "wget", "--quiet", "--output-document=-", "http://127.0.0.1:8123/ping"]), timeout=45)
        target.create("redis", {}, options=["--tmpfs", "/data:rw,size=64m"], command=["redis-server", "--maxmemory-policy", "noeviction"], memory="128m", cpus="0.5")
        target.create("minio", {"MINIO_ROOT_USER": "evalminio", "MINIO_ROOT_PASSWORD": passwords["minio"]},
            options=["--tmpfs", "/data:rw,size=256m,mode=1777"], entrypoint="sh",
            command=["-c", 'mkdir -p /data/langfuse && exec minio server --address ":9000" /data'], memory="512m", cpus="0.5")
        common = {"DATABASE_URL": f"postgresql://eval:{passwords['postgres']}@lf-postgres:5432/eval", "SALT": passwords["salt"],
            "ENCRYPTION_KEY": encryption_key, "TELEMETRY_ENABLED": "false", "LANGFUSE_ENABLE_EXPERIMENTAL_FEATURES": "false",
            "CLICKHOUSE_MIGRATION_URL": "clickhouse://lf-clickhouse:9000", "CLICKHOUSE_URL": "http://lf-clickhouse:8123", "CLICKHOUSE_USER": "eval", "CLICKHOUSE_PASSWORD": passwords["clickhouse"],
            "CLICKHOUSE_CLUSTER_ENABLED": "false", "LANGFUSE_S3_EVENT_UPLOAD_BUCKET": "langfuse", "LANGFUSE_S3_EVENT_UPLOAD_REGION": "auto",
            "LANGFUSE_S3_EVENT_UPLOAD_ACCESS_KEY_ID": "evalminio", "LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY": passwords["minio"],
            "LANGFUSE_S3_EVENT_UPLOAD_ENDPOINT": "http://lf-minio:9000", "LANGFUSE_S3_EVENT_UPLOAD_FORCE_PATH_STYLE": "true",
            "LANGFUSE_S3_MEDIA_UPLOAD_BUCKET": "langfuse", "LANGFUSE_S3_MEDIA_UPLOAD_REGION": "auto", "LANGFUSE_S3_MEDIA_UPLOAD_ACCESS_KEY_ID": "evalminio",
            "LANGFUSE_S3_MEDIA_UPLOAD_SECRET_ACCESS_KEY": passwords["minio"], "LANGFUSE_S3_MEDIA_UPLOAD_ENDPOINT": "http://lf-minio:9000", "LANGFUSE_S3_MEDIA_UPLOAD_FORCE_PATH_STYLE": "true",
            "REDIS_HOST": "lf-redis", "REDIS_PORT": "6379", "NEXTAUTH_URL": "http://lf-web:3000", "NEXTAUTH_SECRET": passwords["nextauth"],
            "LANGFUSE_INGESTION_QUEUE_DELAY_MS": "100", "LANGFUSE_INGESTION_CLICKHOUSE_WRITE_INTERVAL_MS": "1000"}
        web_env = {**common, "LANGFUSE_INIT_ORG_ID": run_id + "-org", "LANGFUSE_INIT_ORG_NAME": "Isolated eval",
            "LANGFUSE_INIT_PROJECT_ID": run_id + "-project", "LANGFUSE_INIT_PROJECT_NAME": "Isolated eval", "LANGFUSE_INIT_PROJECT_PUBLIC_KEY": public_key,
            "LANGFUSE_INIT_PROJECT_SECRET_KEY": secret_key, "LANGFUSE_INIT_USER_EMAIL": "eval@example.invalid", "LANGFUSE_INIT_USER_NAME": "Synthetic eval",
            "LANGFUSE_INIT_USER_PASSWORD": passwords["user"]}
        web = target.create("web", web_env, memory="2g")
        # Docker internal networks deliberately have no published host ports.
        # The host reads the exact owned bridge address, without adding egress.
        address = run(DOCKER + ["inspect", "--format", '{{(index .NetworkSettings.Networks "' + target.network + '").IPAddress}}', web])
        check(ipaddress.ip_address(address).is_private, "Langfuse must use the owned private network")
        check(run(DOCKER + ["network", "inspect", "--format", "{{.Internal}}", target.network]) == "true", "Native target network is not isolated")
        endpoint = "http://" + address + ":3000"
        wait_for(lambda: urlopen(endpoint + "/api/public/health", timeout=3).close(), timeout=180)
        target.create("worker", common, memory="2g")
        runtime.atomic_json(root / "checkpoint.json", {"phase": "target_ready", "run_id": run_id})
        start = time.time_ns()
        producer = target.create("producer", {"NODE_ENV": "test", "ENVIRONMENT": "test", "K3S_EVAL_ENABLED": "1", "K3S_EVAL_RUN_ID": run_id,
            "LANGFUSE_URL": "http://lf-web:3000", "LANGFUSE_PUBLIC_KEY": public_key, "LANGFUSE_SECRET_KEY": secret_key},
            options=["--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,size=32m", "--mount", f"type=bind,src={root / 'trace.mjs'},dst=/trace.mjs,readonly",
                     "--mount", f"type=bind,src={root / 'request.json'},dst=/request.json,readonly"], command=["node", "/trace.mjs"], memory="512m")
        code = run(DOCKER + ["wait", producer])
        logs = target.redact(run(DOCKER + ["logs", producer]))
        (root / "producer.log").write_text(logs)
        check(code == "0" and '"operation_failed":true' in logs, "Real traced operation did not demonstrate the seeded failure")
        iso = lambda stamp: datetime.fromtimestamp(stamp / 1e9, timezone.utc).isoformat()
        native_output = root / "native-events.json"
        collector_env = {"PATH": str(Path.home() / ".local/bin") + ":/usr/bin:/bin", "HOME": str(Path.home()), "NODE_PATH": str(Path.home() / ".local/lib/node_modules"),
            "LANGFUSE_URL": endpoint, "LANGFUSE_PUBLIC_KEY": public_key, "LANGFUSE_SECRET_KEY": secret_key}
        def collect():
            subprocess.run(["tsx", str(PACKAGE / "src/ai_quality/runtime-errors-cli.ts"), "--env", "test", "--start", iso(start), "--end", iso(time.time_ns()),
                "--service", "impression-node", "--repository", "impression", "--output", str(native_output)], env=collector_env,
                text=True, capture_output=True, timeout=30, check=True)
            result = runtime.load(native_output)
            if not result["coverage"]["complete"] or not result["events"]:
                raise ValueError("Actual error observation not ingested yet")
            return result
        population = wait_for(collect, timeout=120)
        check(any("trim" in event["line"] for event in population["events"]), "The native observation does not match the failed operation")
        events = [{**event, "timestamp_ns": int(event["timestamp_ns"])} for event in population["events"]]
        check(all(event["repository"] == "impression" and event["service"] == "impression-node" for event in events), "Native routing failed")
        end = time.time_ns()
        queue.collect(events, end, coverage=[population["coverage"]], source_cursors={"langfuse/impression": end})
        pending = queue.pending()
        check(len(pending) == 1, "Native observation did not group into one incident")
        count = pending[0]["count"]
        queue.collect(events, end + 1)
        check(queue.pending()[0]["count"] == count, "Native replay duplicated an occurrence")
        report["detection"] = {"passed": True, "events": len(events), "groups": 1, "routing": "passed", "replay": "passed", "coverage": population["coverage"],
            "path": "real withAiTrace -> LangfuseSpanProcessor -> isolated Langfuse OTLP ingestion -> actual native API collector -> actual queue"}
        report["window"] = {"start_ns": start, "end_ns": end}
    except BaseException as error:
        report["error"] = target.redact(f"{type(error).__name__}: {error}")
    finally:
        queue.db.close()
        cleaned = target.cleanup()
        report["cleanup"] = {"resources_removed": cleaned, "immutable_sources_unchanged": all(digest(path) == value for path, value in hashes.items())}
        report["finished_ns"] = time.time_ns()
        report["runtime_seconds"] = round((report["finished_ns"] - report["started_ns"]) / 1e9, 2)
        report["passed"] = report.get("detection", {}).get("passed", False) and all(report["cleanup"].values()) and "error" not in report
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
    signal.signal(signal.SIGTERM, lambda _number, _frame: (_ for _ in ()).throw(KeyboardInterrupt("Eval terminated")))
    with runtime.lock(args.output_root / "native-eval.lock"):
        return evaluate(args)


if __name__ == "__main__":
    raise SystemExit(main())
