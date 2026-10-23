#!/usr/bin/env python3
"""Run a deterministic K3s health audit before optionally invoking Codex."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import fcntl
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

PACKAGE = next(parent / "internal/src" for parent in Path(__file__).resolve().parents if (parent / "internal/src/maintenance_runtime.py").is_file())
sys.path.insert(0, str(PACKAGE))
from maintenance_runtime import Queue, atomic_json, config_root, investigate, load, lock as mutation_lock, redact, state_root as maintenance_state, prune_runs
from maintenance_audit import backup_findings, capacity, releases
from maintenance_issues import deliver


def kubectl_json(*args: str, optional: bool = False) -> dict[str, Any]:
    completed = subprocess.run(["kubectl", "--request-timeout=20s", *args, "-o", "json"], text=True, capture_output=True, timeout=30)
    if completed.returncode != 0:
        if optional:
            return {"items": [], "coverage_error": f"Resource query failed: {' '.join(args)}"}
        raise RuntimeError(completed.stderr.strip() or f"kubectl {' '.join(args)} failed")
    return json.loads(completed.stdout)


def state_root() -> Path:
    root = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "ctx9-automation/cluster-wizard"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    return root


def condition_ready(resource: dict[str, Any], condition_type: str = "Ready") -> bool:
    return any(item.get("type") == condition_type and item.get("status") == "True" for item in resource.get("status", {}).get("conditions", []))


def collect(settings: dict[str, Any], cache_root: Path) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []
    def get(*args, optional=False):
        try:
            result = kubectl_json(*args, optional=True)
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            result = {"items": [], "coverage_error": f"Resource query unavailable: {type(error).__name__}"}
        coverage.append({"source": " ".join(args), "complete": "coverage_error" not in result, **({"error": result["coverage_error"]} if "coverage_error" in result else {})})
        return result

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    def recent(item: dict[str, Any]) -> bool:
        stamp = item.get("status", {}).get("completionTime") or item.get("metadata", {}).get("creationTimestamp")
        return bool(stamp and datetime.fromisoformat(stamp.replace("Z", "+00:00")) >= cutoff)

    nodes = get("get", "nodes").get("items", [])
    for node in nodes:
        if not condition_ready(node):
            findings.append({"kind": "Node", "namespace": None, "name": node["metadata"]["name"], "reason": "not Ready"})
        for condition in node.get("status", {}).get("conditions", []):
            if condition.get("type") in {"DiskPressure", "MemoryPressure", "PIDPressure", "NetworkUnavailable"} and condition.get("status") == "True":
                findings.append({"kind": "Node", "namespace": None, "name": node["metadata"]["name"], "reason": condition["type"]})

    workloads = get("get", "deployments,statefulsets,daemonsets", "-A").get("items", [])
    for item in workloads:
        desired = item.get("spec", {}).get("replicas", item.get("status", {}).get("desiredNumberScheduled", 0)) or 0
        ready = item.get("status", {}).get("readyReplicas", item.get("status", {}).get("numberReady", 0)) or 0
        if desired != ready:
            findings.append({"kind": item["kind"], "namespace": item["metadata"].get("namespace"), "name": item["metadata"]["name"], "reason": f"ready {ready}/{desired}"})

    pods = get("get", "pods", "-A").get("items", [])
    for pod in pods:
        phase = pod.get("status", {}).get("phase")
        if phase in {"Pending", "Unknown"} or (phase == "Failed" and recent(pod)):
            findings.append({"kind": "Pod", "namespace": pod["metadata"].get("namespace"), "name": pod["metadata"]["name"], "reason": phase, "created_at": pod["metadata"]["creationTimestamp"]})
        for status in pod.get("status", {}).get("containerStatuses", []):
            waiting = status.get("state", {}).get("waiting", {}).get("reason")
            if waiting in {"CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull", "CreateContainerConfigError"}:
                findings.append({"kind": "Pod", "namespace": pod["metadata"].get("namespace"), "name": pod["metadata"]["name"], "reason": waiting, "created_at": pod["metadata"]["creationTimestamp"]})

    for finding in findings:
        if finding["kind"] == "Pod":
            pod = next(item for item in pods if item["metadata"]["name"] == finding["name"] and item["metadata"]["namespace"] == finding["namespace"])
            owners = pod["metadata"].get("ownerReferences", [])
            if owners:
                owner = owners[0]
                if owner["kind"] == "Job":
                    finding["kind"] = "Job"
                    finding["name"] = re.sub(r"-\d{8,}$", "", owner["name"])
                    if finding["reason"] == "Failed": finding["reason"] = "failed"
                elif owner["kind"] == "ReplicaSet":
                    finding["name"] = re.sub(r"-[a-z0-9]{8,10}$", "", owner["name"])

    jobs = get("get", "jobs", "-A").get("items", [])
    latest_success = {}
    for job in jobs:
        owners = job["metadata"].get("ownerReferences", [])
        if owners and condition_ready(job, "Complete"):
            key = (job["metadata"]["namespace"],owners[0]["name"])
            latest_success[key] = max(latest_success.get(key,""),job["metadata"]["creationTimestamp"])
    for job in jobs:
        owners = job["metadata"].get("ownerReferences", [])
        if owners and latest_success.get((job["metadata"]["namespace"],owners[0]["name"]),"") > job["metadata"]["creationTimestamp"]:
            continue
        if (job.get("status", {}).get("failed") or 0) > 0 and not condition_ready(job, "Complete") and recent(job):
            findings.append({"kind": "Job", "namespace": job["metadata"].get("namespace"), "name": next((owner["name"] for owner in job["metadata"].get("ownerReferences", []) if owner["kind"] == "CronJob"),job["metadata"]["name"]), "reason": "failed"})

    findings = [item for item in findings if not (item["kind"] == "Job" and item.get("created_at") and latest_success.get((item["namespace"],item["name"]),"") > item["created_at"])]

    certificates = get("get", "certificates.cert-manager.io", "-A", optional=True).get("items", [])
    for certificate in certificates:
        if not condition_ready(certificate):
            findings.append({"kind": "Certificate", "namespace": certificate["metadata"].get("namespace"), "name": certificate["metadata"]["name"], "reason": "not Ready"})
        expiry = certificate.get("status", {}).get("notAfter")
        if expiry and datetime.fromisoformat(expiry.replace("Z", "+00:00")) < datetime.now(timezone.utc) + timedelta(days=settings["certificate_expiry_days"]):
            findings.append({"kind": "Certificate", "namespace": certificate["metadata"].get("namespace"), "name": certificate["metadata"]["name"], "reason": "certificate expires within policy horizon", "not_after": expiry})

    clusters = get("get", "clusters.postgresql.cnpg.io", "-A", optional=True).get("items", [])
    for cluster in clusters:
        instances = cluster.get("spec", {}).get("instances", 0)
        ready = cluster.get("status", {}).get("readyInstances", 0)
        if instances != ready:
            findings.append({"kind": "CNPGCluster", "namespace": cluster["metadata"].get("namespace"), "name": cluster["metadata"]["name"], "reason": f"ready {ready}/{instances}"})

    volumes = get("get", "volumes.longhorn.io", "-n", "longhorn-system", optional=True).get("items", [])
    for volume in volumes:
        robustness = volume.get("status", {}).get("robustness")
        if robustness in {"degraded", "faulted"}:
            findings.append({"kind": "LonghornVolume", "namespace": "longhorn-system", "name": volume["metadata"]["name"], "reason": robustness})

    events = get("get", "events", "-A").get("items", [])
    for event in events:
        if event.get("type") != "Warning":
            continue
        stamp = event.get("eventTime") or event.get("lastTimestamp") or event.get("metadata", {}).get("creationTimestamp")
        if not stamp:
            continue
        when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if when >= cutoff:
            observations.append({"kind": "Event", "namespace": event["metadata"].get("namespace"), "name": event.get("involvedObject", {}).get("name"), "reason": event.get("reason", "Warning"), "count": event.get("count", 1)})

    backups = get("get", "backups.postgresql.cnpg.io", "-A", optional=True).get("items", [])
    findings.extend(backup_findings(clusters, backups, settings["backup_max_age_hours"]))
    for check in (capacity(settings), releases(settings, nodes, workloads, clusters, cache_root)):
        new_findings, new_coverage, new_observations = check
        findings.extend(new_findings)
        coverage.extend(new_coverage)
        observations.extend(new_observations)
    coverage.extend([
        {"source": "restore-test-evidence", "complete": False, "error": "Restore-test evidence adapter is not configured"},
        {"source": "postgres-wal-metrics", "complete": False, "error": "WAL-specific metrics are not configured; PVC forecasts are separate"},
    ])
    deduped = list({json.dumps(item, sort_keys=True): item for item in findings}.values())
    event_context = list({json.dumps(item, sort_keys=True): item for item in observations}.values())
    return {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "counts": {"nodes": len(nodes), "workloads": len(workloads), "findings": len(deduped), "observations": len(event_context)},
        "findings": deduped,
        "observations": event_context,
        "coverage": coverage,
    }




def main() -> int:
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["run"])
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args()
    root = state_root()
    with (root / "run.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("cluster audit is already running")
            return 0
        run_dir = root / "runs" / f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{time.time_ns()}"
        run_dir.mkdir(parents=True, mode=0o700)
        settings = load(config_root() / "skills/config/k3s-cluster-wizard/config.json")
        evidence = collect(settings, root / "release-cache")
        path = run_dir / "audit.json"
        atomic_json(path, evidence)
        queue = Queue(root / "state.sqlite3")
        now = time.time_ns()
        events = []
        kind_queries = {
            "Node":"get nodes", "Deployment":"get deployments,statefulsets,daemonsets -A",
            "StatefulSet":"get deployments,statefulsets,daemonsets -A", "DaemonSet":"get deployments,statefulsets,daemonsets -A",
            "Pod":"get pods -A", "Job":"get jobs -A", "Certificate":"get certificates.cert-manager.io -A",
            "CNPGCluster":"get clusters.postgresql.cnpg.io -A", "LonghornVolume":"get volumes.longhorn.io -n longhorn-system",
            "Backup":"get backups.postgresql.cnpg.io -A"}
        complete = {item["source"] for item in evidence["coverage"] if item["complete"]}
        snapshots = ["cluster-audit/"+kind for kind,query in kind_queries.items() if query in complete]
        if "get clusters.postgresql.cnpg.io -A" not in complete and "cluster-audit/Backup" in snapshots:
            snapshots.remove("cluster-audit/Backup")
        for item in evidence["findings"]:
            labels = item.get("labels", {})
            resource = "/".join(str(labels[key]) for key in ("persistentvolumeclaim", "instance", "mountpoint", "disk") if labels.get(key))
            source = "cluster-audit/"+item["kind"]
            if item["kind"] == "Capacity":
                source += "/"+item["name"]
                if item["name"] in complete: snapshots.append(source)
            if item["kind"] == "Upgrade":
                source += "/"+item["name"]
                if "releases/"+item["name"] in complete: snapshots.append(source)
            impact = item["kind"] != "Upgrade"
            events.append({"source": source, "service": f'{item.get("namespace") or "cluster"}/{item["kind"]}/{item["name"]}/{resource}', "repository": "k3s-infrastructure", "timestamp_ns": now, "line": item["reason"], "detail": redact(item), "confirmed_impact": impact, "critical": impact and item["reason"] not in {"Pending"}, "impact": item["reason"]})
        # Successful metric reads can clear a previous failure even when no finding remains.
        snapshots.extend("cluster-audit/Capacity/"+item["source"] for item in evidence["coverage"] if item["complete"])
        for item in evidence["coverage"]:
            source = "coverage/"+item["source"]
            if item["complete"]:
                snapshots.append(source)
            elif "not configured" not in item.get("error", "") and not item["source"].startswith("releases/"):
                events.append({"source":source,"service":"telemetry/"+item["source"],"repository":"k3s-infrastructure","timestamp_ns":now,"line":"Collector unavailable: "+item.get("error","incomplete coverage"),"confirmed_impact":True,"impact":"Maintenance cannot verify this telemetry source"})
        queue.collect(events, now, coverage=evidence["coverage"], snapshot_sources=snapshots)
        if not args.audit_only:
            try:
                with mutation_lock(maintenance_state() / "mutation.lock") as lock_fd:
                    investigate(queue, settings, root, run_dir.name, evidence["coverage"], lock_fd, skill="k3s-cluster-wizard")
            except BlockingIOError:
                print("A maintenance agent is active; audit investigations remain pending")
        delivery = deliver(queue, "cluster-wizard")
        queue.prune()
        prune_runs()
        print(json.dumps({"findings": len(events), "pending": len(queue.pending()), "issues": delivery, "coverage_complete": all(item["complete"] for item in evidence["coverage"])}))
        queue.db.close()
        return 0


if __name__ == "__main__":
    sys.exit(main())
