#!/usr/bin/env python3
"""Install inert Langfuse observability plugins without credential material."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
from typing import Any


CODEX_PLUGIN_ID = "tracing@codex-observability-plugin"
CODEX_MARKETPLACE = "langfuse/codex-observability-plugin"
CLAUDE_PLUGIN_ID = "langfuse-observability@langfuse-observability"
CLAUDE_MARKETPLACE = "langfuse/Claude-Observability-Plugin"
TARGET_METADATA = Path.home() / ".config/ctx9/agents/integrations/langfuse.json"
CODEX_STUB = Path.home() / ".codex/langfuse.json"


class ScaffoldError(RuntimeError):
    pass


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def require_commands() -> None:
    missing = [command for command in ("codex", "claude", "node", "uv") if shutil.which(command) is None]
    if missing:
        raise ScaffoldError(
            "missing required commands: " + ", ".join(missing) + "; install them through their owning approved workflow"
        )


def source_metadata() -> Path:
    if TARGET_METADATA.is_file():
        return TARGET_METADATA
    raise ScaffoldError(
        f"Langfuse instance metadata is missing at {TARGET_METADATA}; run agent configuration sync first"
    )


def load_metadata() -> dict[str, Any]:
    path = source_metadata()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScaffoldError(f"invalid Langfuse instance metadata: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != 2:
        raise ScaffoldError("Langfuse instance metadata needs schema_version 2")
    if value.get("enabled") is not True:
        raise ScaffoldError("Langfuse integration is disabled in instance configuration")
    base_url = value.get("base_url")
    if not isinstance(base_url, str) or not base_url.startswith("https://"):
        raise ScaffoldError("Langfuse instance metadata needs an HTTPS base_url")
    return value


def json_output(command: list[str]) -> Any:
    result = run(command)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "command failed").strip().splitlines()[-1]
        raise ScaffoldError(f"{' '.join(command)}: {detail}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ScaffoldError(f"{' '.join(command)} returned invalid JSON") from exc


def codex_installed() -> bool:
    value = json_output(["codex", "plugin", "list", "--json"])
    installed = value.get("installed") if isinstance(value, dict) else None
    return isinstance(installed, list) and any(
        isinstance(item, dict) and item.get("pluginId") == CODEX_PLUGIN_ID and item.get("installed") is True
        for item in installed
    )


def codex_hooks_enabled() -> bool:
    result = run(["codex", "features", "list"])
    if result.returncode != 0:
        return False
    return any(line.split()[:1] == ["hooks"] and line.split()[-1:] == ["true"] for line in result.stdout.splitlines())


def claude_state() -> tuple[bool, bool]:
    value = json_output(["claude", "plugin", "list", "--json"])
    if not isinstance(value, list):
        return False, False
    for item in value:
        if isinstance(item, dict) and item.get("id") == CLAUDE_PLUGIN_ID:
            return True, item.get("enabled") is True
    return False, False


def codex_stub_value(metadata: dict[str, Any]) -> dict[str, Any]:
    capture = metadata.get("capture_defaults")
    max_chars = capture.get("max_chars", 20000) if isinstance(capture, dict) else 20000
    return {
        "enabled": False,
        "base_url": metadata["base_url"],
        "environment": "coding-agent",
        "tags": ["coding-agent"],
        "max_chars": max_chars,
        "debug": False,
        "fail_on_error": False,
    }


def write_stub(metadata: dict[str, Any]) -> str:
    if CODEX_STUB.exists() or CODEX_STUB.is_symlink():
        return "preserved-existing"
    CODEX_STUB.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    CODEX_STUB.parent.chmod(0o700)
    temporary = CODEX_STUB.with_name(f".{CODEX_STUB.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(codex_stub_value(metadata), indent=2) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    os.replace(temporary, CODEX_STUB)
    return "installed-disabled"


def apply(metadata: dict[str, Any]) -> list[str]:
    changes: list[str] = []
    if not codex_installed():
        for command in (
            ["codex", "plugin", "marketplace", "add", CODEX_MARKETPLACE, "--json"],
            ["codex", "plugin", "add", CODEX_PLUGIN_ID, "--json"],
        ):
            result = run(command)
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "command failed").strip().splitlines()[-1]
                raise ScaffoldError(f"{' '.join(command)}: {detail}")
        changes.append("installed Codex Langfuse plugin")
    if not codex_hooks_enabled():
        result = run(["codex", "features", "enable", "hooks"])
        if result.returncode != 0:
            raise ScaffoldError((result.stderr or result.stdout).strip())
        changes.append("enabled Codex hooks feature")
    stub = write_stub(metadata)
    if stub == "installed-disabled":
        changes.append(f"installed disabled non-secret stub at {CODEX_STUB}")

    claude_installed, claude_enabled = claude_state()
    if not claude_installed:
        for command in (
            ["claude", "plugin", "marketplace", "add", CLAUDE_MARKETPLACE, "--scope", "user"],
            ["claude", "plugin", "install", CLAUDE_PLUGIN_ID, "--scope", "user"],
        ):
            result = run(command)
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "command failed").strip().splitlines()[-1]
                raise ScaffoldError(f"{' '.join(command)}: {detail}")
        claude_enabled = True
        changes.append("installed Claude Langfuse plugin")
    if claude_enabled:
        result = run(["claude", "plugin", "disable", CLAUDE_PLUGIN_ID, "--scope", "user"])
        if result.returncode != 0:
            raise ScaffoldError((result.stderr or result.stdout).strip())
        changes.append("disabled unconfigured Claude Langfuse plugin")
    return changes


def verify() -> dict[str, Any]:
    codex_ready = codex_installed() and codex_hooks_enabled()
    claude_installed, claude_enabled = claude_state()
    stub_ready = CODEX_STUB.is_file() and not CODEX_STUB.is_symlink()
    if stub_ready:
        stub_ready = stat.S_IMODE(CODEX_STUB.stat().st_mode) == 0o600
    return {
        "ready": codex_ready and claude_installed and not claude_enabled and stub_ready,
        "codex_plugin_installed_and_hooks_enabled": codex_ready,
        "claude_plugin_installed_and_disabled": claude_installed and not claude_enabled,
        "disabled_codex_stub_present_with_mode_0600": stub_ready,
        "credentials_enrolled": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    try:
        require_commands()
        metadata = load_metadata()
        if args.dry_run:
            report = verify()
            report.update({"mode": "dry-run", "would_apply": not report["ready"]})
        elif args.verify:
            report = {"mode": "verify", **verify()}
        else:
            changes = apply(metadata)
            report = {"mode": "apply", "changes": changes, **verify()}
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["ready"] or args.dry_run else 1
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)[:1000]}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
