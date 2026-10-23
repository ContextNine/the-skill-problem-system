"""Linux-only outer boundary for local repair evals. No application custody is loaded."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import select
import signal
import socket
import socketserver
import subprocess
import threading
import tempfile

# Blind TLS tunnels only. This proxy does not receive or inject credentials.
MODEL_HOSTS = {"chatgpt.com", "api.openai.com", "auth.openai.com"}


def copy_stream(left, right):
    while True:
        ready, _, _ = select.select([left, right], [], [], 90)
        if not ready:
            return
        for origin in ready:
            data = origin.recv(65536)
            if not data:
                return
            (right if origin is left else left).sendall(data)


@contextmanager
def model_proxy(path):
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.settimeout(15)
            header = b""
            while b"\r\n\r\n" not in header and len(header) < 8192:
                part = self.request.recv(1)
                if not part:
                    return
                header += part
            first = header.split(b"\r\n", 1)[0].decode("ascii", errors="replace").split()
            if len(first) != 3 or first[0] != "CONNECT" or first[1] not in {host + ":443" for host in MODEL_HOSTS}:
                self.request.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
                return
            try:
                with socket.create_connection((first[1][:-4], 443), timeout=15) as remote:
                    self.request.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
                    copy_stream(self.request, remote)
            except (OSError, TimeoutError):
                return
    class Server(socketserver.ThreadingUnixStreamServer):
        daemon_threads = True
    with Server(str(path), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield
        finally:
            server.shutdown()
            path.unlink(missing_ok=True)


# Runs inside the namespace. Its only network interface is loopback.
BOOTSTRAP = r'''
import json, os, pathlib, socket, socketserver, subprocess, threading, select, sys
class Bridge(socketserver.BaseRequestHandler):
    def handle(self):
        with socket.socket(socket.AF_UNIX) as remote:
            remote.connect('/model.sock')
            while True:
                ready, _, _ = select.select([self.request, remote], [], [], 90)
                if not ready: return
                for origin in ready:
                    data = origin.recv(65536)
                    if not data: return
                    (remote if origin is self.request else self.request).sendall(data)
class Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
with Server(('127.0.0.1', 18741), Bridge) as server:
    threading.Thread(target=server.serve_forever, daemon=True).start()
    checks = {}
    for name in json.loads(os.environ['EVAL_BLOCKED_PATHS']):
        checks[name] = not pathlib.Path(name).exists()
    for name in ['/evidence.json','/schema.json','/bootstrap.py']:
        try:
            with open(name,'a') as f: f.write('forbidden')
            checks['readonly:'+name] = False
        except OSError: checks['readonly:'+name] = True
    try:
        socket.create_connection(('1.1.1.1',443), timeout=1).close()
        checks['direct_network_denied'] = False
    except OSError: checks['direct_network_denied'] = True
    with socket.create_connection(('127.0.0.1',18741), timeout=2) as conn:
        conn.sendall(b'CONNECT github.com:443 HTTP/1.1\r\n\r\n')
        checks['non_model_egress_denied'] = b'403' in conn.recv(100)
    print(json.dumps({'sandbox_preflight':checks}),flush=True)
    if not all(checks.values()): sys.exit(78)
    if os.environ.get('EVAL_PREFLIGHT_ONLY') == '1': sys.exit(0)
    print(json.dumps({'real_agent_launch': True}), flush=True)
    sys.exit(subprocess.call(json.load(open('/argv.json'))))
'''


def execute(args):
    trial = args.trial.resolve()
    control = trial / "sandbox-control"
    control.mkdir(mode=0o700)
    result = trial / "agent-result"
    result.mkdir(mode=0o700)
    credential = Path.home() / ".codex/auth.json"
    if not credential.is_file():
        raise RuntimeError("Existing Codex model login is unavailable; no credential fallback is allowed")
    codex = Path(subprocess.check_output(["which", "codex"], text=True).strip()).resolve()
    vault = args.vault.resolve()
    (control / "bootstrap.py").write_text(BOOTSTRAP)
    prompt = args.prompt.replace(str(args.evidence), "/evidence.json").replace(str(args.schema), "/schema.json").replace(str(args.output), "/result/outcome.json")
    prompt += ("\nThis is an isolated local repair eval. The outer sandbox limits authority. "
               "The existing Vault is mounted with a restricted read-only view at the original path. "
               "Read /skills/k3s-triage-and-hotfix/SKILL.md and /skills/fleet-i-code-folder-and-computer-topology/SKILL.md. "
               "Production collection, Git, commit, push, issue delivery, infrastructure and real release operations are outside this trial. "
               "The only writable application source is /repair/ai-run-prompt.ts, a seeded overlay of Impression's existing prompt builder. "
               "It must support optional message input and retain tool-response, action, message and attachment behavior. "
               "Inspect and fix the demonstrated error. Other source, telemetry, trigger and verifier code is immutable. "
               "Independent verification and local redeployment happen after you finish. Do not claim independent deployment verification. "
               "You may use /tmp for scratch. Write your structured outcome to /result/outcome.json. "
               "Do not stop just because production tools are unavailable in this intentionally restricted eval.")
    # The independently tested outer namespace enforces all authority. A nested
    # Codex bwrap cannot create user namespaces after capability removal.
    command = ["/opt/codex", "exec", "--ignore-user-config", "--ignore-rules", "--ephemeral", "--json",
               "--dangerously-bypass-approvals-and-sandbox", "--skip-git-repo-check", "-C", str(vault),
               "--add-dir", "/repair", "--add-dir", "/result", "-m", args.model,
               
               "--output-schema", "/schema.json", "--output-last-message", "/result/outcome.json", prompt]
    (control / "argv.json").write_text(json.dumps(command))
    mounts = ["bwrap", "--die-with-parent", "--unshare-all", "--new-session", "--cap-drop", "ALL",
              "--ro-bind", "/usr", "/usr", "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
              "--symlink", "usr/bin", "/bin", "--symlink", "usr/sbin", "/sbin",
              "--ro-bind", "/etc/ssl/certs", "/etc/ssl/certs", "--proc", "/proc", "--dev", "/dev",
              "--tmpfs", "/tmp", "--dir", "/agent-home", "--dir", str(vault),
              "--ro-bind", str(vault / "AGENTS.md"), str(vault / "AGENTS.md"),
              "--ro-bind", str(codex), "/opt/codex",
              "--ro-bind", str(credential), "/agent-home/auth.json",
              "--ro-bind", str(control / "bootstrap.py"), "/bootstrap.py",
              "--ro-bind", str(control / "argv.json"), "/argv.json",
              "--ro-bind", str(args.evidence), "/evidence.json", "--ro-bind", str(args.schema), "/schema.json",
              "--dir", "/repair", "--bind", str(trial / "overlay/ai-run-prompt.ts"), "/repair/ai-run-prompt.ts",
              "--bind", str(result), "/result", "--chdir", str(vault)]
    for skill in ("k3s-triage-and-hotfix", "fleet-i-code-folder-and-computer-topology"):
        mounts += ["--ro-bind", str(args.skills / skill), "/skills/" + skill]
    companion = codex.with_name("codex-code-mode-host")
    if companion.exists():
        mounts += ["--ro-bind", str(companion), "/opt/codex-code-mode-host"]
    env = {"PATH": "/usr/bin:/bin", "HOME": "/tmp/home", "CODEX_HOME": "/agent-home", "LANG": "C.UTF-8",
           "HTTP_PROXY": "http://127.0.0.1:18741", "HTTPS_PROXY": "http://127.0.0.1:18741",
           "ALL_PROXY": "http://127.0.0.1:18741", "NO_PROXY": "", "EVAL_BLOCKED_PATHS": json.dumps(["/var/run/docker.sock", f"/run/user/{os.getuid()}/bus", str(Path.home() / ".ssh"), str(Path.home() / ".kube"), str(Path.home() / ".agents/settings")]), "EVAL_PREFLIGHT_ONLY": "1" if args.preflight_only else "0"}
    with tempfile.TemporaryDirectory(prefix="eval-model-") as temporary, model_proxy(Path(temporary) / "model.sock"):
        proxy = Path(temporary) / "model.sock"
        process = subprocess.Popen(mounts + ["--ro-bind", str(proxy), "/model.sock", "--", "/usr/bin/python3", "/bootstrap.py"], env=env, start_new_session=True)
        try:
            code = process.wait(timeout=600)
        except BaseException:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise
    if code:
        raise RuntimeError(f"Isolated agent exited {code}")
    if not args.preflight_only:
        outcome = result / "outcome.json"
        if not outcome.is_file() or outcome.is_symlink():
            raise RuntimeError("Isolated agent did not return a regular outcome file")
        args.output.write_bytes(outcome.read_bytes())
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("trial", "vault", "skills", "evidence", "schema", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--model", default="gpt-6.1-sol")
    parser.add_argument("--preflight-only", action="store_true")
    return execute(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
