"""Shared request launcher for manual AI audits and native runtime-error collection."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys

from maintenance_runtime import atomic_json, atomic_text, config_root, load, lock, redact, workspace


def request_root():
    path = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "ctx9-ai-audit"
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def run_profile(args, *, cwd, timeout, pass_fds):
    """Bound the whole managed process group, including descendants holding locks."""
    with subprocess.Popen(args,cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          start_new_session=True,pass_fds=pass_fds) as child:
        try:
            stdout,stderr=child.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid,signal.SIGTERM)
            try:
                child.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid,signal.SIGKILL)
                child.communicate()
            raise RuntimeError(f"Managed telemetry request exceeded {timeout}s; coverage is incomplete")
        return subprocess.CompletedProcess(args,child.returncode,stdout,stderr)


def run_request(repository, mode, environment, arguments, *, operation="audit"):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", repository):
        raise ValueError("Invalid workspace ID")
    adapter = load(config_root() / "skills/config/k3s-ai-triage/repositories.json")["repositories"][repository]
    if environment not in adapter["environments"]:
        raise ValueError("Environment is not configured for this repository")
    if mode == "triage" and operation == "audit" and environment in adapter.get("retention_days", {}):
        arguments = [*arguments, "--retention-days", str(adapter["retention_days"][environment])]
    root = request_root()
    path = root / f"{repository}.json"
    result_path = root / f"{repository}.result.json"
    with lock(root / f"{repository}.lock") as fd:
        result_path.unlink(missing_ok=True)
        request = {"schema_version": 1, "repository": repository, "mode": mode, "environment": environment,
                   "operation": operation, "args": arguments, "created_at": datetime.now(timezone.utc).isoformat()}
        atomic_json(path, request)
        try:
            completed = run_profile(["notenv", "run", adapter["profiles"][mode][environment]], cwd=workspace(repository), timeout=180 if operation == "runtime-errors" else 1200, pass_fds=(fd,))
            if completed.returncode:
                atomic_text(root / f"{repository}.error.log", redact(completed.stderr))
                raise RuntimeError(f"Managed AI request failed with exit {completed.returncode}; telemetry coverage is incomplete")
            if operation == "runtime-errors":
                result = load(result_path)
                result_path.unlink()
                return result
            print(completed.stdout, end="")
            return 0
        finally:
            path.unlink(missing_ok=True)


def consume(repository, mode, environment):
    """Called only inside the target repository's declared Notenv profile."""
    path = request_root() / f"{repository}.json"
    details = path.lstat()
    if not stat.S_ISREG(details.st_mode) or details.st_uid != os.getuid() or details.st_mode & 0o077:
        raise RuntimeError("Unsafe AI request file")
    request = load(path)
    if request.get("schema_version") != 1 or any(request.get(key) != value for key, value in {"repository": repository, "mode": mode, "environment": environment}.items()):
        raise ValueError("AI request does not match the declared profile")
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(request["created_at"].replace("Z", "+00:00"))).total_seconds()
    if not 0 <= age <= 300:
        raise ValueError("AI request is stale")
    args = request["args"]
    operation = request.get("operation", "audit")
    flags = {"--since", "--trace-id", "--workflow", "--action", "--agent", "--release", "--status", "--limit", "--retention-days"}
    if operation == "runtime-errors":
        flags = {"--start", "--end", "--service"}
    elif operation != "audit":
        raise ValueError("Unknown AI operation")
    if not isinstance(args, list) or len(args) > 22 or len(args) % 2 or any(not isinstance(item, str) for item in args):
        raise ValueError("Invalid AI request arguments")
    if any(args[index] not in flags for index in range(0, len(args), 2)):
        raise ValueError("Unsupported AI request flag")
    path.unlink()
    scripts = Path(__file__).resolve().parent / "ai_quality"
    script = "runtime-errors-cli.ts" if operation == "runtime-errors" else "triage-cli.ts" if mode == "triage" else "cli.ts"
    command = ["tsx", str(scripts / script)]
    if mode == "trace":
        command.append("audit")
    command += ["--env", environment, *args]
    if operation == "runtime-errors":
        command += ["--repository", repository, "--output", str(request_root() / f"{repository}.result.json")]
    child_env = {**os.environ, "NODE_PATH": str(Path.home() / ".local/lib/node_modules")}
    return subprocess.run(command, cwd=workspace(repository), env=child_env, check=False).returncode


def main(mode):
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--since", default="7d" if mode == "triage" else "24h")
    if mode == "trace":
        for flag in ("trace-id", "workflow", "action", "agent", "release", "status"):
            parser.add_argument(f"--{flag}")
        parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    match = re.fullmatch(r"([1-9][0-9]?)(h|d)", args.since)
    if not match or int(match[1]) * (24 if match[2] == "d" else 1) > 90 * 24:
        raise ValueError("Interval must be between one hour and ninety days")
    arguments = ["--since", args.since]
    if mode == "trace":
        if not 1 <= args.limit <= 1000:
            raise ValueError("Trace limit must be between 1 and 1000")
        if args.trace_id:
            arguments = []
        for key in ("trace_id", "workflow", "action", "agent", "release", "status", "limit"):
            value = getattr(args, key)
            if value is not None:
                arguments += [f'--{key.replace("_", "-")}', str(value)]
    return run_request(args.repository, mode, args.environment, arguments)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["consume"])
    parser.add_argument("--repository", required=True)
    parser.add_argument("--mode", choices=["triage", "trace"], required=True)
    parser.add_argument("--environment", required=True)
    args = parser.parse_args()
    sys.exit(consume(args.repository, args.mode, args.environment))
