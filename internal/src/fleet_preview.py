#!/usr/bin/env python3
"""Share loopback development servers through a configured private SSH HTTP relay."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import shlex
import signal
import socket
import subprocess
import sys
import time
import uuid

from package_layout import active_instance_root, installed_state_root, read_json


class PreviewError(ValueError):
    pass


def port_number(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("port must be an integer") from exc
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def dns_label(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", value):
        raise PreviewError("preview and machine names must be lowercase DNS labels")
    return value


def configuration(root: Path) -> dict:
    config = read_json(root / "fleet/preview.json", "Fleet preview configuration")
    if config.get("schema_version") != 1 or config.get("enabled") is not True:
        raise PreviewError("public previews are not configured; see $fleet-i-public-dev-preview")
    for field in ("domain", "relay_host", "host_key"):
        if not isinstance(config.get(field), str) or not config[field]:
            raise PreviewError(f"preview configuration needs {field}")
    domain = config["domain"]
    if "." not in domain or len(domain) > 253:
        raise PreviewError("preview domain must be a DNS hostname")
    for label in domain.split("."):
        dns_label(label)
    if not re.fullmatch(r"[a-zA-Z0-9.-]+", config["relay_host"]):
        raise PreviewError("relay_host must be a DNS hostname or IPv4 address")
    config["relay_port"] = port_number(str(config.get("relay_port", 2200)))
    if not re.fullmatch(r"(?:ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp256) [A-Za-z0-9+/]+={0,3}", config["host_key"]):
        raise PreviewError("host_key must contain the relay's public SSH key type and base64 data")
    prefix = config.get("hostname_prefix", "")
    if prefix:
        dns_label(prefix.rstrip("-"))
        if not prefix.endswith("-"):
            raise PreviewError("hostname_prefix must end with a hyphen")
    config["hostname_prefix"] = prefix
    if config.get("viewer_authentication") != "required":
        raise PreviewError("the public route must require viewer authentication before enabling previews")
    return config


def select_machine(root: Path, explicit: str | None) -> dict:
    identity = installed_state_root() / "machine-id"
    selected = explicit or (identity.read_text().strip() if identity.is_file() else "")
    if not selected:
        raise PreviewError("machine identity is missing; use --machine with a registered machine ID")
    dns_label(selected)
    registry = read_json(root / "fleet/machines.json", "machine registry")
    matches = [m for m in registry["machines"] if m.get("id") == selected and m.get("enabled")]
    if len(matches) != 1:
        raise PreviewError(f"machine is not enabled in the fleet registry: {selected}")
    return matches[0]


def state_directory() -> Path:
    directory = installed_state_root() / "previews"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    return directory


@contextmanager
def locked(directory: Path):
    with (directory / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def save(path: Path, record: dict) -> None:
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as stream:
        os.chmod(temporary, 0o600)
        json.dump(record, stream, indent=2)
        stream.write("\n")
    temporary.replace(path)


def owned_process(record: dict) -> bool:
    pid = record.get("pid")
    if not isinstance(pid, int) or pid <= 1:
        return False
    result = subprocess.run(["ps", "-p", str(pid), "-o", "args="], capture_output=True, text=True)
    return result.returncode == 0 and f"fleet_preview.py _run {record['session']}" in result.stdout


def running(record: dict) -> bool:
    return owned_process(record) and record.get("status") == "running"


def require_listener(port: int) -> None:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            pass
    except OSError as exc:
        raise PreviewError(f"no server is listening on 127.0.0.1:{port}; start it before sharing") from exc


def ssh_command(config: dict, record: dict, known_hosts: Path) -> list[str]:
    return [
        "ssh", "-T", "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
        *(["-o", "UseKeychain=yes"] if sys.platform == "darwin" else []),
        "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={known_hosts}",
        "-o", "ConnectTimeout=10", "-o", "ExitOnForwardFailure=yes",
        "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3",
        "-i", str(Path(config["identity_file"]).expanduser()),
        "-p", str(config["relay_port"]), "-R", f":80:127.0.0.1:{record['port']}",
        f"v0@{config['relay_host']}", "http", "--proxy_name", record["name"],
        "--custom_domain", record["hostname"],
    ]


def terminate(record: dict) -> None:
    if not owned_process(record):
        return
    os.killpg(record["pid"], signal.SIGTERM)
    deadline = time.monotonic() + 8
    while owned_process(record) and time.monotonic() < deadline:
        time.sleep(0.1)
    if owned_process(record):
        raise PreviewError("previous preview process has not exited; inspect it before retrying")


def supervisor(session: str, path: Path, config_root: Path) -> int:
    record = read_json(path, "preview session")
    if record["session"] != session:
        raise PreviewError("preview session changed before startup")
    config = configuration(config_root)
    config["identity_file"] = record["identity_file"]
    known_hosts = path.with_suffix(".known_hosts")
    host = config["relay_host"] if config["relay_port"] == 22 else f"[{config['relay_host']}]:{config['relay_port']}"
    known_hosts.write_text(f"{host} {config['host_key']}\n")
    known_hosts.chmod(0o600)
    log_path = path.with_suffix(".log")
    command = ssh_command(config, record, known_hosts)
    stopped = False

    def stop(_signum, _frame):
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    child = None
    try:
        with log_path.open("w") as log:
            log_path.chmod(0o600)
            child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=log)
            deadline = time.monotonic() + 15
            while not stopped and child.poll() is None:
                if record["status"] != "running":
                    output = log_path.read_text(errors="replace")
                    if f"RemoteAddress: {record['hostname']}:" in output:
                        record.update(status="running", ssh_pid=child.pid)
                        save(path, record)
                    elif time.monotonic() >= deadline:
                        record.update(status="failed", error="relay did not confirm registration; inspect the session log")
                        break
                time.sleep(0.1)
            if not stopped:
                record.update(status="failed", error=record.get("error", "SSH forwarding ended; inspect the session log"))
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=3)
        if stopped:
            record.update(status="stopped")
        # An old session must never overwrite a replacement's state.
        if path.exists() and read_json(path, "preview session").get("session") == session:
            save(path, record)
        known_hosts.unlink(missing_ok=True)
    return 0 if stopped else 1


def share(args: argparse.Namespace, root: Path) -> dict:
    config = configuration(root)
    selected = select_machine(root, args.machine)
    machine = selected["id"]
    config["identity_file"] = config.get("identity_file") or selected.get("fleet_shell", {}).get("identity_file")
    if not isinstance(config["identity_file"], str) or not config["identity_file"]:
        raise PreviewError("no SSH identity is configured for this machine")
    name = dns_label(f"{machine}-{args.name or args.port}")
    hostname = f"{config['hostname_prefix']}{name}.{config['domain']}"
    dns_label(hostname.split(".")[0])
    require_listener(args.port)
    directory = state_directory()
    path = directory / f"{name}.json"
    record = {"name": name, "machine": machine, "port": args.port, "hostname": hostname,
              "identity_file": config["identity_file"], "relay_host": config["relay_host"], "relay_port": config["relay_port"],
              "url": f"https://{hostname}", "status": "starting",
              "created": datetime.now(timezone.utc).isoformat(), "session": uuid.uuid4().hex}
    if args.dry_run:
        return {**record, "status": "planned", "command": shlex.join(ssh_command(config, record, path.with_suffix(".known_hosts")))}
    identity = Path(config["identity_file"]).expanduser()
    if not identity.is_file():
        raise PreviewError("configured SSH identity is missing; enrol this machine before sharing")
    with locked(directory):
        if path.exists():
            previous = read_json(path, "preview session")
            if owned_process(previous):
                if running(previous) and all(previous.get(key) == record[key] for key in ("port", "hostname", "relay_host", "relay_port", "identity_file")):
                    return previous
                raise PreviewError("preview name is already active; stop it or choose --name")
        save(path, record)
        child = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "_run", record["session"], str(path), str(root)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
        )
        record["pid"] = child.pid
        # The supervisor waits for this PID assignment before recording readiness.
        save(path, record)
        deadline = time.monotonic() + 18
        while child.poll() is None and time.monotonic() < deadline:
            current = read_json(path, "preview session")
            if current["status"] == "running":
                return current
            if current["status"] == "failed":
                break
            time.sleep(0.1)
        current = read_json(path, "preview session")
        terminate(current)
        child.wait(timeout=8)
        raise PreviewError(f"preview did not start; inspect {path.with_suffix('.log')}")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="fleet preview", description=__doc__)
    root.add_argument("--config-root", type=Path, help=argparse.SUPPRESS)
    commands = root.add_subparsers(dest="action", required=True)
    sharing = commands.add_parser("share", help="share an already running loopback server")
    sharing.add_argument("port", type=port_number)
    sharing.add_argument("--name", type=dns_label, help="optional label instead of the port in the URL")
    sharing.add_argument("--machine", help="registered machine identity, if local identity is unavailable")
    sharing.add_argument("--dry-run", action="store_true")
    sharing.add_argument("--json", action="store_true")
    listing = commands.add_parser("list", help="show this machine's preview sessions")
    listing.add_argument("--json", action="store_true")
    stopping = commands.add_parser("stop", help="stop sharing a port without stopping its dev server")
    stopping.add_argument("port", nargs="?", type=port_number)
    stopping.add_argument("--all", action="store_true")
    stopping.add_argument("--json", action="store_true")
    return root


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw and raw[0] == "preview":
        raw.pop(0)
    try:
        if raw and raw[0] == "_run":
            # The launcher assigns the PID under its lock before the child writes state.
            path = Path(raw[2])
            deadline = time.monotonic() + 3
            while "pid" not in read_json(path, "preview session") and time.monotonic() < deadline:
                time.sleep(0.02)
            return supervisor(raw[1], path, Path(raw[3]))
        args = parser().parse_args(raw)
        root = active_instance_root(args.config_root)
        if args.action == "share":
            result = share(args, root)
            print(json.dumps(result, indent=2) if args.json else result["url"])
            return 0
        directory = state_directory()
        with locked(directory):
            records = [(path, read_json(path, "preview session")) for path in sorted(directory.glob("*.json"))]
            if args.action == "stop":
                if (args.port is None) == (not args.all):
                    raise PreviewError("choose a port or --all")
                records = [(path, record) for path, record in records if args.all or record["port"] == args.port]
                for path, record in records:
                    terminate(record)
                    record.update(status="stopped")
                    save(path, record)
            result = [{**record, "status": record["status"] if owned_process(record) else
                       "failed" if record["status"] == "failed" else "stopped"} for _, record in records]
        if args.json:
            print(json.dumps(result, indent=2))
        elif result:
            for record in result:
                print(f"{record['status']:8} 127.0.0.1:{record['port']}  {record['url']}")
        else:
            print("No preview sessions.")
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"fleet preview: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
