"""Deterministic issue delivery from the local maintenance queue through gh or glab."""
from __future__ import annotations

import hashlib
import json
import subprocess
import time
from urllib.parse import quote, urlparse

from maintenance_runtime import CLOSED, maintenance_settings, redact


def json_documents(value):
    """Both CLIs paginate JSON arrays; glab emits consecutive JSON documents."""
    decoder = json.JSONDecoder()
    values = []
    remaining = value.strip()
    while remaining:
        item, end = decoder.raw_decode(remaining)
        values.extend(item if isinstance(item, list) else [item])
        remaining = remaining[end:].lstrip()
    return values


class IssueClient:
    def __init__(self, config):
        self.provider = config["provider"]
        if self.provider not in {"github", "gitlab"}:
            raise ValueError("Issue provider must be github, gitlab or off")
        self.host = config.get("hostname", "github.com" if self.provider == "github" else "gitlab.com")
        self.repository = config["repository"]
        if not self.host or any(char in self.host for char in "/\r\n "):
            raise ValueError("Issue hostname must be a host, without a URL path")
        if not self.repository or any(part in {"", ".", ".."} for part in self.repository.split("/")):
            raise ValueError("Issue repository must be an explicit owner/project path")
        project = "/".join(quote(part, safe="") for part in self.repository.split("/"))
        self.base = f"repos/{project}/issues" if self.provider == "github" else f"projects/{quote(self.repository, safe='')}/issues"
        self.destination = f"{self.provider}:{self.host}/{self.repository}"
        self.records = None

    def api(self, method, endpoint, payload=None, *, paginate=False):
        args = ["gh" if self.provider == "github" else "glab", "api", "--hostname", self.host,
                "--method", method, endpoint]
        if paginate:
            args.append("--paginate")
        if payload is not None:
            args += ["--input", "-"]
        completed = subprocess.run(args, input=json.dumps(payload) if payload is not None else None,
                                   text=True, capture_output=True, timeout=90)
        if completed.returncode:
            raise RuntimeError(f"{self.provider} issue API failed: {redact(completed.stderr)[:1000]}")
        return json_documents(completed.stdout)

    def find(self, marker):
        query = "state=all&per_page=100" if self.provider == "github" else "scope=all&state=all&per_page=100"
        if self.records is None:
            self.records = self.api("GET", f"{self.base}?{query}", paginate=True)
        matches = [item for item in self.records
                   if marker in (item.get("body" if self.provider == "github" else "description") or "")]
        if len(matches) > 1:
            raise RuntimeError("Multiple issues have the same incident marker; reconcile them before retrying")
        return matches[0] if matches else None

    def save(self, record, title, body, closed):
        payload = {"title": title, "body" if self.provider == "github" else "description": body}
        if record is None:
            result = self.api("POST", self.base, payload)[0]
            if self.records is not None:
                self.records.append(result)
        else:
            number = record["number" if self.provider == "github" else "iid"]
            payload.update({"state": "closed" if closed else "open"} if self.provider == "github"
                           else {"state_event": "close" if closed else "reopen"})
            result = self.api("PATCH" if self.provider == "github" else "PUT", f"{self.base}/{number}", payload)[0]
        return result["number" if self.provider == "github" else "iid"], result["html_url" if self.provider == "github" else "web_url"]


def issue_summary(job, row, *, agent_off=False):
    outcome = json.loads(row["outcome"] or "{}")
    summary = redact(outcome.get("summary") or row["impact"] or "Collected error awaits investigation")
    next_action = redact(outcome.get("next_action") or "Enable a coding agent or investigate this incident manually.")
    marker = f"<!-- ctx9-maintenance:{job}:{row['id']} -->"
    title = f"[{job}] {redact(row['service'])}: {summary.splitlines()[0]}"[:180]
    lines = [marker, f"Status: {row['status']}", "", summary, "", "Next action", "", next_action,
             "", f"Incident: `{row['id']}`", f"Service: `{redact(row['service'])}`"]
    if agent_off:
        lines += ["", "Automatic repair is disabled. No coding agent has investigated this pending incident."]
    if outcome.get("run_id"):
        lines += [f"Run: `{outcome['run_id']}`"]
    verification = [item[:1000] for item in redact(outcome.get("verification", []))[:10]]
    if verification:
        lines += ["", "Verification", "", *[f"- {item}" for item in verification]]
    repositories = [{key: value if isinstance(value, bool) or value is None else str(value)[:500]
                     for key, value in item.items() if key in {"workspace", "initial_sha", "commit", "release", "verified"}}
                    for item in redact(outcome.get("repositories", []))[:10]]
    if repositories:
        lines += ["", "Repository results", "", "```json", json.dumps(repositories, indent=2), "```"]
    if row["status"] == "closed" and row["impact"]:
        lines += ["", f"Recovery proof: {redact(row['impact'])}"]
    body = "\n".join(lines) + "\n"
    digest = hashlib.sha256(body.encode()).hexdigest()
    return marker, title, body, digest


def deliver(queue, job, *, force=False):
    settings = maintenance_settings()
    config = settings.get("issues", {"provider": "off"})
    if config.get("provider", "off") == "off":
        return {"delivered": 0, "failed": 0, "disabled": True}
    client = IssueClient(config)
    agent_off = settings.get("agent", {}).get("provider") == "off"
    rows = queue.db.execute("SELECT * FROM incidents ORDER BY first_ns,id").fetchall()
    result = {"delivered": 0, "failed": 0}
    for row in rows:
        saved = queue.db.execute("SELECT * FROM issue_delivery WHERE destination=? AND incident_id=?",
                                 (client.destination, row["id"])).fetchone()
        eligible = row["status"] in {"blocked", "unresolved", "approval_required"} or (agent_off and row["status"] == "pending")
        if saved is None and not eligible:
            continue
        # A queued delivery can resolve before an issue was created. Keep its local history.
        if row["status"] in CLOSED and (saved is None or saved["issue_number"] is None):
            continue
        marker, title, body, digest = issue_summary(job, row, agent_off=agent_off and row["status"] == "pending")
        if saved and (saved["published_hash"] == digest or (not force and saved["next_attempt_ns"] > time.time_ns())):
            continue
        if saved is None:
            with queue.db:
                queue.db.execute("INSERT INTO issue_delivery(destination,incident_id) VALUES (?,?)", (client.destination, row["id"]))
        try:
            # Discover by marker before creation, including after an ambiguous API timeout.
            record = ({"number" if client.provider == "github" else "iid": saved["issue_number"]}
                      if saved and saved["issue_number"] else client.find(marker))
            if record is None and row["status"] in CLOSED:
                continue
            number, url = client.save(record, title, body, row["status"] in CLOSED)
            parsed = urlparse(url)
            if parsed.scheme != "https" or parsed.netloc != client.host:
                raise ValueError("Issue API returned an unexpected issue URL")
            with queue.db:
                queue.db.execute("UPDATE issue_delivery SET issue_number=?,url=?,published_hash=?,attempts=0,next_attempt_ns=0,error=NULL WHERE destination=? AND incident_id=?",
                                 (number, url, digest, client.destination, row["id"]))
            result["delivered"] += 1
        except Exception as error:
            attempts = (saved["attempts"] if saved else 0) + 1
            delay = min(6 * 3600, 60 * 2 ** min(attempts, 8))
            with queue.db:
                queue.db.execute("UPDATE issue_delivery SET attempts=?,next_attempt_ns=?,error=? WHERE destination=? AND incident_id=?",
                                 (attempts, time.time_ns() + delay * 10**9, redact(str(error)), client.destination, row["id"]))
            result["failed"] += 1
    return result
