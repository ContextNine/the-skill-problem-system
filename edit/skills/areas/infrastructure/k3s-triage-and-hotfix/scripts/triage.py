#!/usr/bin/env python3
"""Collect managed-service failures and drain durable investigations in existing Code checkouts."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
from urllib.parse import urlencode, urlsplit
from urllib.request import urlopen

PACKAGE = next(parent / "internal/src" for parent in Path(__file__).resolve().parents if (parent / "internal/src/maintenance_runtime.py").is_file())
sys.path.insert(0, str(PACKAGE))
from maintenance_runtime import Queue, atomic_json, command, config_root, investigate, load, lock, redact, state_root, prune_runs
from maintenance_ai import run_request
from maintenance_issues import deliver


def timestamp_ns(value):
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 10**9)


def correlation(line):
    matches = re.findall(r'''(?i)["']?(?:trace[_-]?id|request[_-]?id)["']?\s*[:=]\s*["']?([\w-]{8,})''', line)
    return sorted({hashlib.sha256(value.encode()).hexdigest() for value in matches})


def service_for(config, namespace, labels):
    app = labels.get("app") or labels.get("app.kubernetes.io/name") or labels.get("app_kubernetes_io_name")
    for item in config["services"]:
        if item["namespace"] == namespace and item["app"] == app:
            return item["id"], item.get("workspace")
    owner = app or labels.get("container") or labels.get("pod") or "unknown"
    return f"{namespace}/{owner}", None


def loki_query_telemetry(service, line):
    # Loki logs its own search expression, including our error regex, at info level.
    return service == "monitoring/loki" and bool(re.match(r"level=(?:info|debug)\b", line)) and " query=" in line


def filter_queued_query_telemetry(queue):
    """Retain already collected false positives without sending them to Codex."""
    rows = queue.db.execute("SELECT id,service,evidence FROM incidents WHERE status='pending' AND service='monitoring/loki'").fetchall()
    filtered = [row["id"] for row in rows if loki_query_telemetry(row["service"], json.loads(row["evidence"])["line"])]
    with queue.db:
        queue.db.executemany("UPDATE incidents SET status='filtered' WHERE id=?", ((identity,) for identity in filtered))
    return len(filtered)


def loki_events(config, namespace, start, end):
    settings = config["loki"]
    limit = int(settings.get("limit_per_service", 1000))
    events = {}
    budget = 128

    def query(left, right):
        nonlocal budget
        budget -= 1
        if budget < 0:
            raise RuntimeError(f"Loki page budget exhausted for {namespace}; coverage incomplete")
        pattern = json.dumps(r"(?i)\berror\b|unhandled|uncaught|fatal|\[CLIENT")
        expression = f'{{namespace={json.dumps(namespace)}}} |~ {pattern}'
        if namespace == "monitoring":
            # Exclude Loki's logged search expressions before pagination as well.
            expression += ' !~ "^level=(info|debug) .* query="'
        params = urlencode({"query": expression, "start": left, "end": right, "limit": limit, "direction": "forward"})
        endpoint = f'/api/v1/namespaces/{settings["namespace"]}/services/http:{settings["service"]}:{settings["port"]}/proxy/loki/api/v1/query_range?{params}'
        if settings.get("test_url"):
            # A test transport uses the same query, pagination, normalization and routing.
            # It can never select a shared or production destination.
            url = urlsplit(settings["test_url"])
            if config.get("test_only") is not True or url.scheme != "http" or url.hostname != "127.0.0.1" or not url.port or url.path or url.query or url.fragment or url.username or url.password:
                raise ValueError("Direct Loki eval transport requires an explicit loopback test target")
            with urlopen(f'{settings["test_url"]}/loki/api/v1/query_range?{params}', timeout=30) as response:
                payload = json.load(response)
        else:
            payload = json.loads(command(["kubectl", "get", "--raw", endpoint]))
        if payload.get("status") != "success":
            raise RuntimeError(f"Loki query failed for {namespace}")
        streams = payload.get("data", {}).get("result", [])
        if sum(len(stream.get("values", [])) for stream in streams) >= limit:
            if left >= right:
                raise RuntimeError(f"Loki timestamp overflow for {namespace}; coverage incomplete")
            middle = (left + right) // 2
            query(left, middle)
            query(middle + 1, right)
            return
        for stream in streams:
            service, repository = service_for(config, namespace, stream.get("stream", {}))
            for stamp, line in stream.get("values", []):
                if loki_query_telemetry(service, line):
                    continue
                clean = re.sub(r"(?i)\b[0-9a-f]{8}-[0-9a-f-]{27,}\b|\b[0-9a-f]{24,64}\b", "<id-redacted>", redact(line))
                event = {"source": "loki", "timestamp_ns": int(stamp), "service": service, "repository": repository, "line": clean, "correlation": correlation(line)}
                events[(stamp, service, str(stream.get("stream")), line)] = event

    query(start, end)
    return list(events.values())


def collect(config, start, end, cursors=None):
    cursors = cursors or {}
    events, coverage, health, retired = [], [], {}, {}
    try:
        namespace_items = json.loads(command(["kubectl", "get", "namespaces", "-o", "json"]))["items"]
        namespace_names = sorted(item["metadata"]["name"] for item in namespace_items)
        if not namespace_names:
            raise ValueError("Namespace inventory is empty")
        coverage.append({"source": "kubernetes-namespaces", "complete": True, "namespaces": namespace_names})
    except Exception as error:
        coverage.append({"source": "kubernetes-namespaces", "complete": False, "error": redact(str(error))})
    try:
        pods = json.loads(command(["kubectl", "get", "pods", "-A", "-o", "json"]))["items"]
        namespaces = {pod["metadata"]["namespace"] for pod in pods}
        for pod in pods:
            meta, status = pod["metadata"], pod.get("status", {})
            # Completed job attempts are immutable history; the audit checks current job/backup health.
            if any(owner["kind"] == "Job" for owner in meta.get("ownerReferences", [])):
                continue
            service, repository = service_for(config, meta["namespace"], meta.get("labels", {}))
            if status.get("phase") in {"Failed", "Succeeded"}:
                retired[service] = {"retired": True, "proof": "Terminal pod run retained as execution history"}
                continue
            healthy = status.get("phase") == "Succeeded" or (status.get("phase") == "Running" and any(item.get("type") == "Ready" and item.get("status") == "True" for item in status.get("conditions", [])))
            if not meta.get("deletionTimestamp") and status.get("phase") != "Succeeded":
                previous = health.get(service, {"healthy": True})
                health[service] = {"healthy": previous["healthy"] and healthy, "proof": "Live pod readiness for owning service", "revision": str(meta.get("labels", {}).get("pod-template-hash", ""))}
            reasons = {item.get("state", {}).get("waiting", {}).get("reason") for item in status.get("containerStatuses", []) + status.get("initContainerStatuses", [])}
            if status.get("phase") in {"Failed", "Unknown"}:
                reasons.add(status["phase"])
            for reason in reasons & {"Failed", "Unknown", "CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull", "CreateContainerConfigError"}:
                events.append({"source": "kubernetes", "timestamp_ns": end, "service": service, "repository": repository, "line": f"Pod failure: {reason}", "resource": meta["name"], "critical": True, "confirmed_impact": True})
        health.update({service:proof for service,proof in retired.items() if service not in health})
        coverage.append({"source": "kubernetes-pods", "complete": True})
    except Exception as error:
        namespaces = set()
        coverage.append({"source": "kubernetes-pods", "complete": False, "error": redact(str(error))})
    namespaces.update(item["namespace"] for item in config["services"])
    for namespace in sorted(namespaces):
        try:
            events.extend(loki_events(config, namespace, cursors.get(f"loki/{namespace}", start), end))
            coverage.append({"source": f"loki/{namespace}", "complete": True})
        except Exception as error:
            coverage.append({"source": f"loki/{namespace}", "complete": False, "error": redact(str(error))})
    try:
        warnings = json.loads(command(["kubectl", "get", "events", "-A", "--field-selector", "type=Warning", "-o", "json"]))["items"]
        for item in warnings:
            stamp = item.get("series", {}).get("lastObservedTime") or item.get("lastTimestamp") or item.get("eventTime") or item["metadata"]["creationTimestamp"]
            when = timestamp_ns(stamp)
            if cursors.get("kubernetes-events", start) <= when <= end:
                resource = item.get("involvedObject", {})
                namespace = item["metadata"].get("namespace", "cluster")
                events.append({"source": "kubernetes", "timestamp_ns": when, "service": f'{namespace}/{resource.get("kind", "unknown")}', "namespace": namespace, "repository": None, "line": redact(f'{item.get("reason", "Warning")}: {item.get("message", "")}'), "resource": resource.get("name")})
        coverage.append({"source": "kubernetes-events", "complete": True})
    except Exception as error:
        coverage.append({"source": "kubernetes-events", "complete": False, "error": redact(str(error))})
    for adapter in config.get("langfuse", []):
        source = f'langfuse/{adapter["workspace"]}'
        # Delayed reads and overlap cover asynchronous ingestion. Event IDs deduplicate replay.
        upper = end - adapter["settle_minutes"] * 60 * 10**9
        lower = min(cursors.get(source, start), upper) - adapter["overlap_minutes"] * 60 * 10**9
        iso = lambda value: datetime.fromtimestamp(value / 10**9, timezone.utc).isoformat()
        try:
            result = run_request(adapter["workspace"], "triage", adapter["environment"],
                                 ["--start", iso(lower), "--end", iso(upper), "--service", adapter["service"]],
                                 operation="runtime-errors")
            for event in result["events"]:
                event["timestamp_ns"] = int(event["timestamp_ns"])
                if event["service"] != adapter["service"] or event["repository"] != adapter["workspace"] or not lower <= event["timestamp_ns"] < upper:
                    raise ValueError("Native collector returned evidence outside its configured scope")
            if result["coverage"]["complete"] is not True:
                raise RuntimeError("Native collector reported incomplete coverage")
            events.extend(redact(event) for event in result["events"])
            coverage.append({**result["coverage"], "source": source, "cursor_ns": upper})
        except Exception as error:
            coverage.append({"source": source, "complete": False, "error": redact(str(error))})
    for item in coverage:
        if item["complete"]:
            item.setdefault("cursor_ns", end)
    for event in events:
        event["confirmed_impact"] = event.get("confirmed_impact", False) or health.get(event["service"], {}).get("healthy") is False
    for item in coverage:
        if not item["complete"]:
            events.append({"source": "coverage/"+item["source"], "service": "telemetry/"+item["source"], "repository": "k3s-infrastructure", "timestamp_ns": end, "line": "Collector unavailable: "+item.get("error", "incomplete coverage"), "confirmed_impact": True, "impact": "Maintenance cannot verify this telemetry source"})
    return events, coverage, health




def execute(args):
    os.umask(0o077)
    config = load(config_root() / "skills/config/k3s-triage-and-hotfix/config.json")
    if args.dry_run:
        # Do not initialize/migrate the live database during a preview.
        path = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "ctx9-automation/triage/state.sqlite3"
        end = time.time_ns()
        start = end - config["window_minutes"] * 60 * 10**9
        cursors = {}
        if path.is_file():
            with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
                row = db.execute("SELECT value FROM metadata WHERE key='cursor_ns'").fetchone()
                if row:
                    start = int(row[0])
                cursors = {key.removeprefix("cursor:"): int(value) for key, value in db.execute("SELECT key,value FROM metadata WHERE key LIKE 'cursor:%'")}
        events, coverage, health = collect(config, start, end, cursors)
        print(json.dumps({"events": len(events), "coverage": coverage}))
        return 0
    root = state_root() / "triage"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with lock(root / "run.lock"):
        queue = Queue(root / "state.sqlite3")
        end = time.time_ns()
        stored = queue.db.execute("SELECT value FROM metadata WHERE key='cursor_ns'").fetchone()
        start = int(stored[0]) if stored else end - config["window_minutes"] * 60 * 10**9
        cursors = {row["key"].removeprefix("cursor:"): int(row["value"]) for row in queue.db.execute("SELECT key,value FROM metadata WHERE key LIKE 'cursor:%'")}
        events, coverage, health = collect(config, start, end, cursors)
        complete = all(item["complete"] for item in coverage)
        queue.collect(events, end, health=health, coverage=coverage,
                      source_cursors={item["source"]: item["cursor_ns"] if item["complete"] else cursors.get(item["source"], start) for item in coverage},
                      snapshot_sources=["coverage/"+item["source"] for item in coverage if item["complete"]])
        filtered = filter_queued_query_telemetry(queue)
        run_id = f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{time.time_ns()}"
        atomic_json(root / "collection.json", {"run_id": run_id, "start_ns": start, "end_ns": end, "events": len(events), "coverage": coverage})
        if not args.collect_only:
            try:
                with lock(state_root() / "mutation.lock") as lock_fd:
                    investigate(queue, config, root, run_id, coverage, lock_fd)
            except BlockingIOError:
                print("Another maintenance agent owns the mutation lock; investigations remain pending")
        delivery = deliver(queue, "triage")
        queue.prune()
        prune_runs()
        print(json.dumps({"events": len(events), "filtered": filtered, "pending": len(queue.pending()), "issues": delivery, "coverage_complete": all(item["complete"] for item in coverage)}))
        queue.db.close()
        return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["run"])
    parser.add_argument("--collect-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    try:
        return execute(parser.parse_args())
    except BlockingIOError:
        print("Triage is already running")
        return 0


if __name__ == "__main__":
    sys.exit(main())
