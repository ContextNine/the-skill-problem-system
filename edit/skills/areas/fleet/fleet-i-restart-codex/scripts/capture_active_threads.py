"""Save a complete live-daemon active-thread inventory before restarting Codex."""

import argparse
import base64
import datetime
import hashlib
import json
import os
from pathlib import Path
import queue
import socket
import struct
import sys
import threading
import time


class Rpc:
    def __init__(self, socket_path):
        self.socket = socket.socket(socket.AF_UNIX)
        self.socket.settimeout(30)
        self.socket.connect(str(socket_path))
        self.reader = self.socket.makefile("rb")
        self.writer = self.socket.makefile("wb")
        self.messages = queue.Queue()
        self.sequence = 0
        self.write_lock = threading.Lock()
        self.websocket_key = base64.b64encode(os.urandom(16)).decode()
        threading.Thread(target=self._read, daemon=True).start()

    def initialize(self):
        handshake = (
            "GET / HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\n"
            "Connection: Upgrade\r\nSec-WebSocket-Version: 13\r\n"
            f"Sec-WebSocket-Key: {self.websocket_key}\r\n\r\n"
        )
        self.writer.write(handshake.encode())
        self.writer.flush()
        ready = self.messages.get(timeout=30)
        if isinstance(ready, Exception):
            raise ready
        if ready != "connected":
            raise RuntimeError("Daemon closed before WebSocket upgrade completed")
        self.call("initialize", {
            "clientInfo": {"name": "fleet-codex-restart", "version": "1"},
            "capabilities": {"experimentalApi": True},
        })
        self.send({"method": "initialized"})

    def _read(self):
        try:
            stream = self.reader
            status_line = stream.readline()
            if b" 101 " not in status_line:
                raise RuntimeError(f"Daemon rejected WebSocket upgrade: {status_line!r}")
            headers = {}
            while True:
                line = stream.readline()
                if line == b"\r\n":
                    break
                if not line:
                    raise EOFError("Daemon closed during WebSocket upgrade")
                key, value = line.decode().split(":", 1)
                headers[key.lower()] = value.strip()
            expected = base64.b64encode(hashlib.sha1(
                (self.websocket_key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()
            ).digest()).decode()
            if headers.get("sec-websocket-accept") != expected:
                raise RuntimeError("Invalid daemon WebSocket handshake")
            print("Connected to live daemon WebSocket", file=sys.stderr, flush=True)
            self.messages.put("connected")
            data = bytearray()
            while True:
                first, second = self._exact(2)
                length = second & 127
                if second & 128:
                    raise RuntimeError("Unexpected masked server frame")
                if length == 126:
                    length = struct.unpack("!H", self._exact(2))[0]
                elif length == 127:
                    length = struct.unpack("!Q", self._exact(8))[0]
                if length + len(data) > 32 * 1024 * 1024:
                    raise RuntimeError("Daemon inventory response exceeds 32 MiB")
                payload = self._exact(length)
                opcode = first & 15
                if opcode == 8:
                    return
                if opcode == 9:
                    self._frame(payload, opcode=10)
                    continue
                if opcode == 10:
                    continue
                if opcode not in {0, 1} or first & 112:
                    raise RuntimeError("Unsupported daemon WebSocket frame")
                data.extend(payload)
                if first & 128:
                    self.messages.put(json.loads(data))
                    data.clear()
        except Exception as error:
            self.messages.put(error)
        finally:
            self.messages.put(None)

    def _exact(self, count):
        result = bytearray()
        while len(result) < count:
            chunk = self.reader.read(count - len(result))
            if not chunk:
                raise EOFError("Codex proxy closed")
            result.extend(chunk)
        return bytes(result)

    def _frame(self, payload, opcode=1):
        size = len(payload)
        header = bytes([128 | opcode])
        if size < 126:
            header += bytes([128 | size])
        elif size <= 65535:
            header += bytes([128 | 126]) + struct.pack("!H", size)
        else:
            header += bytes([128 | 127]) + struct.pack("!Q", size)
        mask = os.urandom(4)
        masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
        with self.write_lock:
            self.writer.write(header + mask + masked)
            self.writer.flush()

    def send(self, message):
        self._frame(json.dumps({"jsonrpc": "2.0", **message}).encode())

    def call(self, method, params):
        print(f"Reading live daemon: {method}", file=sys.stderr, flush=True)
        self.sequence += 1
        request_id = self.sequence
        self.send({"id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + 30
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"{method} did not respond within 30 seconds")
            try:
                message = self.messages.get(timeout=remaining)
            except queue.Empty as error:
                raise TimeoutError(f"{method} did not respond within 30 seconds") from error
            if message is None:
                raise RuntimeError(f"Codex proxy exited during {method}")
            if isinstance(message, Exception):
                raise message
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise RuntimeError(f"{method}: {message['error']}")
            return message["result"]

    def close(self):
        self.socket.shutdown(socket.SHUT_RDWR)
        self.writer.close()
        self.socket.close()


def pages(rpc, method, params):
    cursor = None
    seen = set()
    while True:
        result = rpc.call(method, {**params, "cursor": cursor})
        yield from result["data"]
        cursor = result.get("nextCursor")
        if not cursor:
            return
        if cursor in seen:
            raise RuntimeError(f"Repeated pagination cursor from {method}")
        seen.add(cursor)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", required=True, type=Path,
                        help="Control socket from codex app-server daemon version")
    parser.add_argument("--host-id", required=True, help="Exact native chat-tool host ID")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; preserve it and use a new snapshot path")
    rpc = None
    try:
        rpc = Rpc(args.socket)
        rpc.initialize()
        loaded = set(pages(rpc, "thread/loaded/list", {"limit": 100}))
        threads = {row["id"]: row for row in pages(rpc, "thread/list", {
            "limit": 100, "sourceKinds": [], "useStateDbOnly": True,
        })}
        for thread_id in loaded - threads.keys():
            threads[thread_id] = rpc.call("thread/read", {"threadId": thread_id})["thread"]
        active = []
        for row in threads.values():
            status = row.get("status", {}).get("type")
            if status not in {"active", "idle", "notLoaded", "systemError"}:
                raise RuntimeError(f"Unknown runtime status for {row['id']}: {status}")
            if status == "active":
                active.append({
                    "threadId": row["id"], "hostId": args.host_id,
                    "title": row.get("name") or row.get("preview", "").split("\n")[0][:160],
                    "cwd": row.get("cwd"), "status": row["status"],
                    "message": None, "verification": None,
                })
        record = {
            "capturedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "socketPath": str(args.socket), "hostId": args.host_id,
            "enumeratedThreads": len(threads), "loadedThreads": len(loaded),
            "activeThreads": sorted(active, key=lambda row: row["threadId"]),
        }
        args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(record, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        print(json.dumps(record, indent=2))
    finally:
        if rpc is not None:
            rpc.close()


if __name__ == "__main__":
    main()
