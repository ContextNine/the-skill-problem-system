#!/usr/bin/env python3
"""Change selected idle chats' working directories through native Codex RPC."""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import selectors
import shutil
import sqlite3
import subprocess
import tempfile
import time


class Client:
    def __init__(self, command: str):
        self.process = subprocess.Popen([command, "app-server", "--stdio"], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        self.sequence = 0
        self.buffer = b""
        try:
            self.call("initialize", {"clientInfo": {"name": "fleet_project_relocation", "version": "1.0"},
                                     "capabilities": {"experimentalApi": True}})
            self.process.stdin.write(b'{"method":"initialized"}\n')
            self.process.stdin.flush()
        except BaseException:
            self.close()
            raise

    def call(self, method: str, params: dict) -> dict:
        self.sequence += 1
        request_id = self.sequence
        self.process.stdin.write((json.dumps({"id": request_id, "method": method, "params": params}) + "\n").encode())
        self.process.stdin.flush()
        deadline = time.monotonic() + 60
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdout, selectors.EVENT_READ)
            while time.monotonic() < deadline:
                while b"\n" in self.buffer:
                    line, self.buffer = self.buffer.split(b"\n", 1)
                    response = json.loads(line)
                    if response.get("id") == request_id:
                        if "error" in response:
                            raise RuntimeError(response["error"])
                        return response["result"]
                if not selector.select(max(0, deadline - time.monotonic())):
                    break
                data = os.read(self.process.stdout.fileno(), 65536)
                if not data:
                    raise RuntimeError("Codex app-server closed its RPC stream")
                self.buffer += data
        raise TimeoutError(method)

    def close(self) -> None:
        self.process.stdin.close()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=10)
        self.process.stdout.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", default="codex")
    parser.add_argument("--codex-home", type=Path, default=Path.home() / ".codex")
    parser.add_argument("--from-cwd", required=True)
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--thread", action="append", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    destination = Path(args.cwd)
    if not destination.is_absolute() or not destination.is_dir():
        raise SystemExit("destination must be an existing absolute directory on this host")
    home = args.codex_home.expanduser().resolve()
    db = home / "state_5.sqlite"
    connection = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    rows = []
    for thread_id in dict.fromkeys(args.thread):
        row = connection.execute("select * from threads where id = ?", (thread_id,)).fetchone()
        if row is None or row["cwd"] not in (args.from_cwd, args.cwd):
            raise SystemExit(f"missing thread or unexpected source directory: {thread_id}")
        if row["archived"]:
            raise SystemExit(f"archived thread needs a separate archive-preserving procedure: {thread_id}")
        rows.append(dict(row))
    report = {"mode": "apply" if args.apply else "preview", "thread_ids": [r["id"] for r in rows],
              "from_cwd": args.from_cwd, "cwd": args.cwd}
    if not args.apply:
        print(json.dumps(report, indent=2))
        connection.close()
        return
    backup_root = home / "thread-port-backups"
    backup_root.mkdir(exist_ok=True, mode=0o700)
    backup = Path(tempfile.mkdtemp(prefix="cwd-edit-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ-"), dir=backup_root))
    destination_db = sqlite3.connect(backup / db.name)
    connection.backup(destination_db)
    destination_db.close()
    for row in rows:
        rollout = Path(row["rollout_path"])
        if not rollout.is_file():
            raise SystemExit(f"missing transcript: {row['id']}")
        shutil.copy2(rollout, backup / (row["id"] + ".jsonl"))
    (backup / "rows.json").write_text(json.dumps(rows, indent=2) + "\n")
    os.chmod(backup / "rows.json", 0o600)
    client = Client(args.codex)
    report.update(backup=str(backup), completed=[])
    try:
        for row in rows:
            response = client.call("thread/resume", {"threadId": row["id"], "cwd": args.cwd, "excludeTurns": True})
            thread = response["thread"]
            if thread["id"] != row["id"] or thread["cwd"] != args.cwd:
                raise RuntimeError(f"resume changed identity or retained old cwd: {row['id']}")
            actual = connection.execute("select id,cwd,archived,is_pinned from threads where id = ?", (row["id"],)).fetchone()
            if dict(actual) != {"id": row["id"], "cwd": args.cwd, "archived": row["archived"], "is_pinned": row["is_pinned"]}:
                raise RuntimeError(f"persisted identity, cwd, pin or archive state mismatch: {row['id']}")
            report["completed"].append(row["id"])
    finally:
        client.close()
        connection.close()
        (backup / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        os.chmod(backup / "report.json", 0o600)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
