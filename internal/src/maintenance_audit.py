"""Deterministic capacity forecasts, backup checks and release candidates."""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import stat
import time
from urllib.parse import urlencode
from urllib.request import urlopen

from maintenance_runtime import atomic_json, command, load, redact


def forecast(samples, *, minimum_hours=24, minimum_coverage=0.8):
    points = sorted({float(stamp): float(value) for stamp, value in samples if math.isfinite(float(value))}.items())
    if len(points) < 2:
        return {"known": False, "reason": "Insufficient samples"}
    duration = points[-1][0] - points[0][0]
    coverage = min(1, len(points) / (duration / 3600 + 1))
    if duration < minimum_hours * 3600 or coverage < minimum_coverage:
        return {"known": False, "reason": "Insufficient history", "samples": len(points), "coverage": coverage}
    xs = [stamp - points[0][0] for stamp, _ in points]
    ys = [value for _, value in points]
    xmean, ymean = sum(xs) / len(xs), sum(ys) / len(ys)
    denominator = sum((value - xmean) ** 2 for value in xs)
    slope = sum((x - xmean) * (y - ymean) for x, y in zip(xs, ys)) / denominator
    return {"known": True, "samples": len(points), "coverage": coverage, "available_per_day": slope * 86400,
            "days_to_exhaustion": max(0, ys[-1]) / (-slope * 86400) if slope < 0 else None}


def prometheus(settings, query, *, history=False):
    params = {"query": query}
    if history:
        params.update(start=int(time.time()) - 7 * 86400, end=int(time.time()), step=3600)
    endpoint = "query_range" if history else "query"
    uri = f'/api/v1/namespaces/{settings["namespace"]}/services/http:{settings["service"]}:{settings["port"]}/proxy/api/v1/{endpoint}?{urlencode(params)}'
    payload = json.loads(command(["kubectl", "get", "--raw", uri]))
    if payload.get("status") != "success":
        raise RuntimeError("Prometheus query failed")
    return payload["data"]["result"]


def metric_key(metric):
    return tuple(sorted((key, value) for key, value in metric.items() if key != "__name__"))


def capacity(settings):
    findings, coverage, observations = [], [], []
    for item in settings["capacity_metrics"]:
        try:
            free = prometheus(settings["prometheus"], item["available"])
            total = {metric_key(value["metric"]): float(value["value"][1]) for value in prometheus(settings["prometheus"], item["capacity"])}
            history = {metric_key(value["metric"]): value["values"] for value in prometheus(settings["prometheus"], item["available"], history=True)}
            if not free:
                raise RuntimeError("No metric series; capacity is unknown")
            missing = 0
            for value in free:
                key = metric_key(value["metric"])
                size = total.get(key)
                available = float(value["value"][1])
                if size is None or size <= 0 or not math.isfinite(size) or not math.isfinite(available):
                    missing += 1
                    continue
                prediction = forecast(history.get(key, []))
                if not prediction["known"]:
                    missing += 1
                labels = value["metric"]
                policy = {**settings["capacity_policy"], **settings.get("capacity_overrides", {}).get(labels.get("namespace", ""), {})}
                used_fraction = 1 - available / size
                observation = {"kind": "Capacity", "name": item["name"], "labels": labels, "available": available, "capacity": size, "used_fraction": used_fraction, "forecast": prediction}
                observations.append(observation)
                days = prediction.get("days_to_exhaustion")
                reasons = []
                if used_fraction >= policy["used_fraction"]:
                    reasons.append("utilization threshold exceeded")
                minimum_free = min(policy["minimum_free_bytes"], size * policy.get("minimum_free_fraction", 0.1))
                if item.get("unit") == "bytes" and available < minimum_free:
                    reasons.append("minimum free capacity breached")
                if days is not None and days <= policy["days_to_exhaustion"]:
                    reasons.append("forecast exhaustion within policy horizon")
                if reasons:
                    findings.append({**observation, "namespace": labels.get("namespace"), "reason": "; ".join(reasons)})
            coverage.append({"source": item["name"], "complete": missing == 0, "unknown_series": missing})
        except Exception as error:
            coverage.append({"source": item["name"], "complete": False, "error": redact(str(error))})
    return findings, coverage, observations


def backup_findings(clusters, backups, max_age_hours):
    findings = []
    now = datetime.now(timezone.utc)
    for cluster in clusters:
        meta = cluster["metadata"]
        stamps = [cluster.get("status", {}).get("lastSuccessfulBackup")]
        for backup in backups:
            if backup["metadata"]["namespace"] != meta["namespace"] or backup.get("spec", {}).get("cluster", {}).get("name") != meta["name"]:
                continue
            status = backup.get("status", {})
            if status.get("phase") == "completed":
                stamps.append(status.get("stoppedAt"))
        parsed = [datetime.fromisoformat(stamp.replace("Z", "+00:00")) for stamp in stamps if stamp]
        age = (now - max(parsed)).total_seconds() / 3600 if parsed else None
        if age is None or age > max_age_hours:
            findings.append({"kind": "Backup", "namespace": meta["namespace"], "name": meta["name"], "reason": "backup freshness unknown" if age is None else "backup is stale", "age_hours": age})
    return findings


def database_checks(settings, clusters, evidence_root):
    """Read primary-only WAL metrics and independently produced restore receipts."""
    findings, coverage, observations = [], [], []
    policy = settings["database_policy"]
    wal_errors, restore_errors = [], []
    if not clusters:
        wal_errors.append("No CNPG clusters discovered")
        restore_errors.append("No CNPG clusters discovered")
    for cluster in clusters:
        meta = cluster["metadata"]
        identity = {"namespace": meta["namespace"], "name": meta["name"]}
        primary = cluster.get("status", {}).get("currentPrimary")
        try:
            if not primary:
                raise ValueError("Current primary is unknown")
            selector = f'namespace={json.dumps(meta["namespace"])},pod={json.dumps(primary)}'
            def read(metric, extra=""):
                expression = f'{metric}{{{selector}{extra}}}'
                fresh = f'({expression}) and (time() - timestamp({expression}) < {policy["metric_max_age_seconds"]})'
                rows = prometheus(settings["prometheus"], fresh)
                values = []
                for row in rows:
                    number = float(row["value"][1])
                    if not math.isfinite(number) or number < 0:
                        raise ValueError("Non-finite or negative WAL metric")
                    values.append((row["metric"], number))
                return values
            size = read("cnpg_collector_pg_wal", ',value="size"')
            age = read("cnpg_pg_stat_archiver_seconds_since_last_archival")
            retained = read("cnpg_pg_replication_slots_pg_wal_lsn_diff")
            active = read("cnpg_pg_replication_slots_active")
            slots = lambda rows: {(labels["slot_name"], labels["slot_type"]): value for labels, value in rows}
            retained_slots, active_slots = slots(retained), slots(active)
            if len(size) != 1 or len(age) != 1 or len(retained_slots) < policy["minimum_slot_series"] or retained_slots.keys() != active_slots.keys():
                raise ValueError("Missing, stale or mismatched primary WAL metric series")
            if len(retained_slots) != len(retained) or len(active_slots) != len(active):
                raise ValueError("Duplicate primary WAL slot series")
            if any(value not in (0, 1) for value in active_slots.values()):
                raise ValueError("Invalid replication slot activity metric")
            reasons = []
            if size[0][1] >= policy["max_wal_bytes"]:
                reasons.append("WAL directory exceeds policy")
            if age[0][1] >= policy["max_archive_age_seconds"]:
                reasons.append("WAL archival is stale")
            slot_observations = []
            for key, retained_bytes in retained_slots.items():
                is_active = bool(active_slots[key])
                slot_observations.append({"slot": key[0], "type": key[1], "active": is_active, "retained_bytes": retained_bytes})
                if retained_bytes >= policy["max_retained_bytes"] or (not is_active and retained_bytes >= policy["max_inactive_retained_bytes"]):
                    reasons.append(f"replication slot {key[0]} retains excessive WAL")
            observation = {"kind": "PostgresWAL", **identity, "primary": primary,
                           "wal_bytes": size[0][1], "archive_age_seconds": age[0][1], "slots": slot_observations}
            observations.append(observation)
            if reasons:
                findings.append({**observation, "reason": "; ".join(reasons)})
        except (KeyError, TypeError, ValueError, OSError, RuntimeError) as error:
            wal_errors.append(f'{meta["namespace"]}/{meta["name"]}: {redact(str(error))}')

        # A backup success is not restore proof. Receipts come from the owning
        # restore verifier, outside the maintenance agent's output directory.
        try:
            uid = meta["uid"]
            if not re.fullmatch(r"[a-zA-Z0-9-]+", uid):
                raise ValueError("Invalid cluster UID")
            path = Path(evidence_root) / f"{uid}.json"
            details = path.lstat()
            if not stat.S_ISREG(details.st_mode) or details.st_uid != os.getuid() or details.st_mode & 0o077 or details.st_size > 65536:
                raise ValueError("Restore receipt must be a bounded private regular file owned by this account")
            receipt = load(path)
            if not isinstance(receipt, dict) or receipt.get("schema_version") != 1 or receipt.get("source_cluster_uid") != uid:
                raise ValueError("Restore receipt does not identify this cluster")
            if receipt.get("status") != "passed" or receipt.get("cleanup_verified") is not True:
                raise ValueError("Restore or cleanup verification did not pass")
            if not all(isinstance(receipt.get(key), str) and receipt[key].strip() for key in ("backup_id", "target", "verifier", "completed_at")):
                raise ValueError("Restore receipt lacks backup, target or verifier evidence")
            completed = datetime.fromisoformat(receipt["completed_at"].replace("Z", "+00:00"))
            if completed.tzinfo is None:
                raise ValueError("Restore receipt timestamp has no timezone")
            age_hours = (datetime.now(timezone.utc) - completed).total_seconds() / 3600
            if not 0 <= age_hours <= policy["restore_max_age_hours"]:
                raise ValueError("Restore evidence is stale or future-dated")
            observations.append({"kind": "RestoreTest", **identity, "receipt": str(path),
                                 "backup_id": receipt["backup_id"], "completed_at": receipt["completed_at"], "verifier": receipt["verifier"]})
        except (KeyError, TypeError, ValueError, OSError) as error:
            reason = "Restore-test evidence unavailable" if isinstance(error, OSError) else str(error)
            restore_errors.append(f'{meta["namespace"]}/{meta["name"]}: {reason}')
            findings.append({"kind": "RestoreTest", **identity, "reason": reason,
                             "next_action": "Run the owning isolated restore procedure and save its independently verified receipt"})
    for source, errors in (("postgres-wal-metrics", wal_errors), ("restore-test-evidence", restore_errors)):
        coverage.append({"source": source, "complete": not errors, **({"error": "; ".join(errors)} if errors else {})})
    return findings, coverage, observations


def version(value):
    match = re.search(r"(?:^|:|/|v)(\d+)\.(\d+)(?:\.(\d+))?(?:\+k3s(\d+))?(?:$|@|-)", value)
    return tuple(int(part or 0) for part in match.groups()) if match else None


def releases(settings, nodes, workloads, clusters, cache_root):
    findings, coverage, observations = [], [], []
    images = [container["image"] for item in workloads for container in item.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])]
    for policy in settings["releases"]:
        try:
            if policy["id"] == "k3s":
                current = sorted({node["status"]["nodeInfo"]["kubeletVersion"] for node in nodes})
            elif policy["id"] == "postgres":
                current = sorted({item["spec"].get("imageName", "") for item in clusters})
            else:
                current = sorted({image for image in images if any(prefix in image for prefix in policy["image_matches"])})
            if not current or any(version(value) is None for value in current):
                raise RuntimeError("Current version is missing or not a supported semantic version")
            cache = cache_root / f'{policy["id"]}-{datetime.now(timezone.utc).date().isoformat()}-v3.json'
            if cache.is_file():
                cached = load(cache)
                available, complete = cached["releases"], cached["complete"]
            else:
                if policy["id"] == "postgres":
                    with urlopen("https://www.postgresql.org/versions.json", timeout=30) as response:
                        raw = json.load(response)
                    available = [{"tag": f'{item["major"]}.{item["latestMinor"]}', "url": "https://www.postgresql.org/support/versioning/", "eol": item["eolDate"]} for item in raw if item["supported"]]
                    complete = True
                else:
                    raw = []
                    page_limit = int(policy.get("page_limit", 20))
                    if not 1 <= page_limit <= 50:
                        raise ValueError("Release page limit must be between one and fifty")
                    complete = False
                    for page in range(1, page_limit+1):
                        batch = json.loads(command(["gh", "api", f'repos/{policy["github"]}/releases?per_page=100&page={page}']))
                        if not isinstance(batch, list):
                            raise ValueError("Release API did not return a page")
                        raw.extend(batch)
                        if len(batch) < 100:
                            complete = True
                            break
                    available = [{"tag": item["tag_name"], "url": item["html_url"]} for item in raw if not item["draft"] and not item["prerelease"] and version(item["tag_name"])]
                if not available:
                    raise RuntimeError("No supported release candidates returned")
                atomic_json(cache, {"releases": available, "complete": complete})
            for deployed in current:
                parsed = version(deployed)
                candidates = [candidate for candidate in available if version(candidate["tag"]) > parsed]
                # Prefer supported patch updates before proposing larger jumps.
                prefix = 1 if policy["id"] == "postgres" else 2
                patches = [candidate for candidate in candidates if version(candidate["tag"])[:prefix] == parsed[:prefix]]
                same_major = [candidate for candidate in candidates if version(candidate["tag"])[0] == parsed[0]]
                candidate = max(patches or same_major or candidates, key=lambda item: version(item["tag"]), default=None)
                observations.append({"service": policy["id"], "current": deployed, "candidate": candidate})
                if candidate:
                    target = version(candidate["tag"])
                    approval = target[0] != parsed[0] or (policy["id"] in {"k3s", "cnpg"} and target[:2] != parsed[:2])
                    findings.append({"kind": "Upgrade", "name": policy["id"], "namespace": None, "reason": "release candidate needs compatibility review", "current": deployed, "candidate": candidate, "approval_required": approval, "compatibility": "unverified; review release notes, backups and owning upgrade procedure"})
            coverage.append({"source": f'releases/{policy["id"]}', "complete": complete})
        except Exception as error:
            coverage.append({"source": f'releases/{policy["id"]}', "complete": False, "error": redact(str(error))})
    return findings, coverage, observations
