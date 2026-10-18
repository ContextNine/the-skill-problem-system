#!/usr/bin/env python3
"""Resolve and preflight registered hotfix repositories, then observe Release."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

PACKAGE = next(parent / "internal/src" for parent in Path(__file__).resolve().parents if (parent / "internal/src/maintenance_runtime.py").is_file())
sys.path.insert(0, str(PACKAGE))
from maintenance_runtime import workspace


def run(args: list[str], cwd: Path | None = None) -> str:
    return subprocess.run(args, cwd=cwd, check=True, text=True, capture_output=True).stdout.strip()


def config_root() -> Path:
    override = os.environ.get("CTX9_AUTOMATION_CONFIG_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    return Path(run(["fleet", "config", "path"])).expanduser().resolve()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def resolve(repository: str) -> tuple[Path, dict[str, Any]]:
    root = config_root()
    workspaces = load(root / "fleet/workspaces.json")["entries"]
    policies = load(root / "skills/config/k3s-hotfix-deploy/repositories.json")["repositories"]
    if repository not in policies or repository not in workspaces:
        raise RuntimeError(f"repository is not registered for hotfix deployment: {repository}")
    checkout = workspace(repository)
    return checkout, policies[repository]


def preflight(repository: str) -> dict[str, Any]:
    checkout, policy = resolve(repository)
    if not checkout.is_dir():
        raise RuntimeError(f"checkout is missing: {checkout}")
    branch = run(["git", "branch", "--show-current"], checkout)
    if branch != "master":
        raise RuntimeError(f"{repository} must be on master, found {branch or 'detached HEAD'}")
    initial_changes = run(["git", "status", "--porcelain=v1"], checkout)
    run(["git", "fetch", "--quiet", "origin", "master"], checkout)
    head = run(["git", "rev-parse", "HEAD"], checkout)
    upstream = run(["git", "rev-parse", "origin/master"], checkout)
    if head != upstream:
        raise RuntimeError(f"{repository} master is not exactly aligned with origin/master")
    result = {"repository": repository, "checkout": str(checkout), "head": head, "initial_changes": initial_changes, **policy}
    print(json.dumps(result, indent=2))
    return result


def observe(repository: str, sha: str, timeout: int) -> int:
    _, policy = resolve(repository)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        raw = run([
            "gh", "run", "list", "--repo", policy["github"], "--workflow", policy["workflow"],
            "--commit", sha, "--limit", "1", "--json", "databaseId,status,conclusion,url,headSha",
        ])
        runs = json.loads(raw)
        if runs:
            item = runs[0]
            if item["status"] == "completed":
                print(json.dumps(item, indent=2))
                return 0 if item["conclusion"] == "success" else 1
        time.sleep(15)
    raise RuntimeError(f"timed out waiting for Release for {repository}@{sha}")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("preflight")
    check.add_argument("--repository", required=True)
    wait = sub.add_parser("observe-release")
    wait.add_argument("--repository", required=True)
    wait.add_argument("--sha", required=True)
    wait.add_argument("--timeout", type=int, default=7200)
    args = parser.parse_args()
    if args.command == "preflight":
        preflight(args.repository)
        return 0
    if len(args.sha) != 40 or any(char not in "0123456789abcdef" for char in args.sha):
        raise RuntimeError("--sha must be a full lowercase Git commit")
    return observe(args.repository, args.sha, args.timeout)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
