#!/usr/bin/env python3
"""Audit package-manager posture and known advisories for a JS/TS repo."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


SEVERITIES = ("critical", "high", "moderate", "low", "info")
SEVERITY_RANK = {name: index for index, name in enumerate(SEVERITIES)}


def run(cmd: list[str], cwd: Path) -> dict[str, Any]:
    try:
        proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, timeout=120)
        return {
            "cmd": " ".join(cmd),
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "missing": False,
        }
    except FileNotFoundError:
        return {"cmd": " ".join(cmd), "returncode": 127, "stdout": "", "stderr": "command not found", "missing": True}
    except subprocess.TimeoutExpired as exc:
        return {
            "cmd": " ".join(cmd),
            "returncode": 124,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "command timed out",
            "missing": False,
        }


def load_json_file(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def parse_json_output(output: str) -> dict[str, Any] | None:
    output = output.strip()
    if not output:
        return None
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        start = output.find("{")
        end = output.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(output[start : end + 1])
            except json.JSONDecodeError:
                return None
    return None


def find_package_jsons(root: Path) -> list[Path]:
    ignored = {"node_modules", ".git", ".next", "dist", "build", "coverage"}
    found: list[Path] = []
    for current, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in ignored]
        if "package.json" in files:
            found.append(Path(current) / "package.json")
    return sorted(found)


def detect_package_manager(root: Path, package_jsons: list[Path]) -> dict[str, Any]:
    root_pkg = load_json_file(root / "package.json") or {}
    package_manager = root_pkg.get("packageManager")
    lockfiles = {
        "pnpm": (root / "pnpm-lock.yaml").exists(),
        "npm": (root / "package-lock.json").exists() or (root / "npm-shrinkwrap.json").exists(),
        "yarn": (root / "yarn.lock").exists(),
        "bun": (root / "bun.lock").exists() or (root / "bun.lockb").exists(),
    }
    manager = None
    version = None
    exact_pin = False
    if isinstance(package_manager, str) and "@" in package_manager:
        manager, version = package_manager.rsplit("@", 1)
        exact_pin = bool(re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", version))
    elif lockfiles["pnpm"]:
        manager = "pnpm"
    elif lockfiles["npm"]:
        manager = "npm"
    elif lockfiles["yarn"]:
        manager = "yarn"
    elif lockfiles["bun"]:
        manager = "bun"

    nested_pins = []
    for pkg_path in package_jsons:
        data = load_json_file(pkg_path) or {}
        value = data.get("packageManager")
        if value:
            nested_pins.append({"path": str(pkg_path.relative_to(root)), "packageManager": value})

    return {
        "manager": manager,
        "version": version,
        "packageManager": package_manager,
        "exactPin": exact_pin,
        "lockfiles": lockfiles,
        "pins": nested_pins,
    }


def scan_pnpm_policy(root: Path) -> dict[str, Any]:
    path = root / "pnpm-workspace.yaml"
    if not path.exists():
        return {"present": False}
    text = path.read_text(errors="replace")
    keys = [
        "minimumReleaseAge",
        "minimumReleaseAgeStrict",
        "minimumReleaseAgeIgnoreMissingTime",
        "strictDepBuilds",
        "verifyStoreIntegrity",
        "onlyBuiltDependencies",
        "ignoredBuiltDependencies",
    ]
    return {
        "present": True,
        "settings": {key: bool(re.search(rf"(?m)^\s*{re.escape(key)}\s*:", text)) for key in keys},
    }


def scan_lockfile_sources(root: Path) -> list[dict[str, str]]:
    patterns = [
        re.compile(r"https?://[^\s'\"]+"),
        re.compile(r"git\+[^\\s'\"]+"),
        re.compile(r"github:[^\s'\"]+"),
    ]
    findings: list[dict[str, str]] = []
    for rel in ("pnpm-lock.yaml", "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "bun.lock"):
        path = root / rel
        if not path.exists():
            continue
        for i, line in enumerate(path.read_text(errors="replace").splitlines(), start=1):
            if any(p.search(line) for p in patterns):
                findings.append({"file": rel, "line": str(i), "text": line.strip()[:220]})
                if len(findings) >= 50:
                    return findings
    return findings


def normalize_pnpm_audit(data: dict[str, Any]) -> dict[str, Any]:
    metadata = data.get("metadata", {})
    counts = metadata.get("vulnerabilities", {})
    advisories = []
    for advisory in (data.get("advisories") or {}).values():
        paths = []
        for finding in advisory.get("findings") or []:
            paths.extend(finding.get("paths") or [])
        advisories.append(
            {
                "severity": advisory.get("severity", "unknown"),
                "package": advisory.get("module_name"),
                "title": advisory.get("title"),
                "patched": advisory.get("patched_versions"),
                "url": advisory.get("url"),
                "paths": sorted(set(paths))[:5],
            }
        )
    return {"counts": counts, "advisories": sort_advisories(advisories)}


def normalize_npm_audit(data: dict[str, Any]) -> dict[str, Any]:
    metadata = data.get("metadata", {})
    counts = metadata.get("vulnerabilities", {})
    advisories = []
    for name, vuln in (data.get("vulnerabilities") or {}).items():
        via = vuln.get("via") or []
        advisory_via = [item for item in via if isinstance(item, dict)]
        if advisory_via:
            for item in advisory_via:
                advisories.append(
                    {
                        "severity": item.get("severity") or vuln.get("severity", "unknown"),
                        "package": name,
                        "title": item.get("title"),
                        "patched": item.get("range"),
                        "url": item.get("url"),
                        "paths": [name],
                    }
                )
        else:
            advisories.append(
                {
                    "severity": vuln.get("severity", "unknown"),
                    "package": name,
                    "title": "Transitive vulnerability",
                    "patched": None,
                    "url": None,
                    "paths": [name],
                }
            )
    return {"counts": counts, "advisories": sort_advisories(advisories)}


def sort_advisories(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda x: (SEVERITY_RANK.get(x.get("severity"), 99), str(x.get("package") or "")))


def run_audit(root: Path, manager: str | None, include_dev: bool) -> dict[str, Any]:
    if manager == "pnpm":
        cmd = ["pnpm", "audit", "--json"]
        if not include_dev:
            cmd.insert(2, "--prod")
        result = run(cmd, root)
        parsed = parse_json_output(result["stdout"])
        return {"tool": "pnpm", "command": result["cmd"], "returncode": result["returncode"], "parsed": normalize_pnpm_audit(parsed) if parsed else None, "stderr": result["stderr"]}
    if manager == "npm":
        cmd = ["npm", "audit", "--json"]
        if not include_dev:
            cmd.append("--omit=dev")
        result = run(cmd, root)
        parsed = parse_json_output(result["stdout"])
        return {"tool": "npm", "command": result["cmd"], "returncode": result["returncode"], "parsed": normalize_npm_audit(parsed) if parsed else None, "stderr": result["stderr"]}
    if manager == "yarn":
        result = run(["yarn", "npm", "audit", "--json"], root)
        return {"tool": "yarn", "command": result["cmd"], "returncode": result["returncode"], "parsed": None, "stderr": result["stderr"] or result["stdout"][:1000]}
    if manager == "bun":
        result = run(["bun", "audit", "--json"], root)
        return {"tool": "bun", "command": result["cmd"], "returncode": result["returncode"], "parsed": None, "stderr": result["stderr"] or result["stdout"][:1000]}
    return {"tool": None, "command": None, "returncode": None, "parsed": None, "stderr": "No supported package manager detected"}


def risk_notes(pm: dict[str, Any], pnpm_policy: dict[str, Any], exotic: list[dict[str, str]]) -> list[str]:
    notes = []
    if not pm.get("packageManager"):
        notes.append("Root package.json has no packageManager pin.")
    elif not pm.get("exactPin"):
        notes.append(f"packageManager is not an exact semver pin: {pm.get('packageManager')}")
    if pm.get("manager") == "pnpm":
        settings = pnpm_policy.get("settings") or {}
        for key in ("minimumReleaseAge", "strictDepBuilds", "verifyStoreIntegrity"):
            if not settings.get(key):
                notes.append(f"pnpm setting not explicit: {key}")
    if exotic:
        notes.append(f"Lockfile contains {len(exotic)} URL/git-like source entries; review for expected direct dependencies.")
    return notes


def render_markdown(report: dict[str, Any]) -> str:
    audit = report["audit"]
    parsed = audit.get("parsed") or {}
    advisories = parsed.get("advisories") or []
    counts = parsed.get("counts") or {}
    lines = [
        "# Repo Security Audit",
        "",
        f"- Root: `{report['root']}`",
        f"- Package manager: `{report['packageManager'].get('packageManager') or report['packageManager'].get('manager') or 'unknown'}`",
        f"- Audit command: `{audit.get('command') or 'not run'}`",
        f"- Audit exit code: `{audit.get('returncode')}`",
        "",
        "## Vulnerability Counts",
        "",
    ]
    if counts:
        for sev in SEVERITIES:
            lines.append(f"- {sev}: {counts.get(sev, 0)}")
    else:
        lines.append("- No parsed audit counts available.")
    lines.extend(["", "## Top Advisories", ""])
    for item in advisories[:20]:
        lines.append(f"- **{item.get('severity')}** `{item.get('package')}`: {item.get('title') or 'Untitled'}")
        if item.get("patched"):
            lines.append(f"  Patched/affected range info: `{item.get('patched')}`")
        if item.get("url"):
            lines.append(f"  {item.get('url')}")
        if item.get("paths"):
            lines.append(f"  Path: `{item['paths'][0]}`")
    if not advisories:
        lines.append("- No parsed advisories.")
    lines.extend(["", "## Install And Supply-Chain Risk", ""])
    notes = report["riskNotes"]
    if notes:
        lines.extend(f"- {note}" for note in notes)
    else:
        lines.append("- No obvious package-manager posture issues detected by this helper.")
    if report["exoticSources"]:
        lines.append("")
        lines.append("Sample URL/git lockfile entries:")
        for entry in report["exoticSources"][:10]:
            lines.append(f"- `{entry['file']}:{entry['line']}` {entry['text']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", nargs="?", default=".", help="Repository root")
    parser.add_argument("--include-dev", action="store_true", help="Include dev dependencies where supported")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args()

    root = Path(args.repo).resolve()
    package_jsons = find_package_jsons(root)
    pm = detect_package_manager(root, package_jsons)
    pnpm_policy = scan_pnpm_policy(root)
    exotic = scan_lockfile_sources(root)
    audit = run_audit(root, pm.get("manager"), args.include_dev)
    report = {
        "root": str(root),
        "packageJsonCount": len(package_jsons),
        "packageManager": pm,
        "pnpmPolicy": pnpm_policy,
        "exoticSources": exotic,
        "audit": audit,
        "riskNotes": risk_notes(pm, pnpm_policy, exotic),
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render_markdown(report))

    parsed = audit.get("parsed") or {}
    counts = parsed.get("counts") or {}
    return 1 if counts.get("critical", 0) or counts.get("high", 0) else 0


if __name__ == "__main__":
    sys.exit(main())
