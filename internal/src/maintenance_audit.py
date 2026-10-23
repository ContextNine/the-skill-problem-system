"""Deterministic capacity forecasts, backup checks and release candidates."""
from datetime import datetime, timezone
import json
import math
import re
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
            cache = cache_root / f'{policy["id"]}-{datetime.now(timezone.utc).date().isoformat()}-v2.json'
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
                    raw = json.loads(command(["gh", "api", f'repos/{policy["github"]}/releases?per_page=100']))
                    available = [{"tag": item["tag_name"], "url": item["html_url"]} for item in raw if not item["draft"] and not item["prerelease"] and version(item["tag_name"])]
                    complete = len(raw) < 100
                if not available:
                    raise RuntimeError("No supported release candidates returned")
                atomic_json(cache, {"releases": available, "complete": complete})
            for deployed in current:
                parsed = version(deployed)
                candidates = [candidate for candidate in available if version(candidate["tag"]) > parsed]
                # Prefer supported patch updates before proposing larger jumps.
                prefix = 1 if policy["id"] == "postgres" else 2
                patches = [candidate for candidate in candidates if version(candidate["tag"])[:prefix] == parsed[:prefix]]
                candidate = max(patches or candidates, key=lambda item: version(item["tag"]), default=None)
                observations.append({"service": policy["id"], "current": deployed, "candidate": candidate})
                if candidate:
                    target = version(candidate["tag"])
                    approval = target[0] != parsed[0] or (policy["id"] in {"k3s", "cnpg"} and target[:2] != parsed[:2])
                    findings.append({"kind": "Upgrade", "name": policy["id"], "namespace": None, "reason": "release candidate needs compatibility review", "current": deployed, "candidate": candidate, "approval_required": approval, "compatibility": "unverified; review release notes, backups and owning upgrade procedure"})
            coverage.append({"source": f'releases/{policy["id"]}', "complete": complete})
        except Exception as error:
            coverage.append({"source": f'releases/{policy["id"]}', "complete": False, "error": redact(str(error))})
    return findings, coverage, observations
