from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
import uuid


WORKMUX = Path(__file__).parent.parent / "assets/terminal-workspaces/workmux"


class WorkmuxTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.bin = self.root / "bin"
        self.home.mkdir()
        self.bin.mkdir()
        self.socket = "workmux-test-" + uuid.uuid4().hex
        real_tmux = shutil.which("tmux")
        assert real_tmux
        (self.bin / "tmux").write_text(f'#!/bin/sh\nexec "{real_tmux}" -L "{self.socket}" "$@"\n')
        (self.bin / "tmux").chmod(0o755)
        real_btop = shutil.which("btop")
        assert real_btop
        shutil.copyfile(real_btop, self.bin / "btop")
        (self.bin / "btop").chmod(0o755)
        self.env = os.environ.copy()
        self.env.update({"HOME": str(self.home), "PATH": f"{self.bin}:/usr/bin:/bin"})

    def tearDown(self):
        subprocess.run([str(self.bin / "tmux"), "kill-server"], env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.temporary.cleanup()

    def tmux(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run([str(self.bin / "tmux"), *args], env=self.env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check)

    def run_workmux(self, session: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["/bin/sh", str(WORKMUX), session], env=self.env, text=True, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def install_restore(self, body: str) -> Path:
        restore = self.home / ".local/share/workmux/plugins/tmux-resurrect/scripts/restore.sh"
        restore.parent.mkdir(parents=True)
        restore.write_text("#!/bin/sh\n" + body)
        restore.chmod(0o755)
        return restore

    def test_repairs_shell_process_in_named_btop_window(self):
        self.tmux("new-session", "-d", "-s", "repair", "-n", "btop")
        self.tmux("new-window", "-d", "-t", "repair:1", "-n", "shell")
        self.run_workmux("repair")
        process = self.tmux("display-message", "-p", "-t", "repair:0.0", "#{pane_current_command}").stdout.strip()
        self.assertEqual(process, "btop")

    def test_preserves_managed_hidden_btop_idle_process(self):
        self.tmux("new-session", "-d", "-s", "idle", "-n", "btop", "/bin/sleep", "86400")
        self.tmux("new-window", "-d", "-t", "idle:1", "-n", "shell")
        self.run_workmux("idle")
        process = self.tmux("display-message", "-p", "-t", "idle:0.0", "#{pane_current_command}").stdout.strip()
        self.assertEqual(process, "sleep")

    def test_refuses_unexpected_window_zero(self):
        self.tmux("new-session", "-d", "-s", "unsafe", "-n", "codex")
        result = self.run_workmux("unsafe")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing to replace unexpected window 0:codex", result.stderr)
        self.assertEqual(self.tmux("display-message", "-p", "-t", "unsafe:0", "#{window_name}").stdout.strip(), "codex")

    def test_concurrent_start_uses_one_locked_restore(self):
        count = self.root / "restore-count"
        self.install_restore(f'sleep 1\nprintf "restore\\n" >> "{count}"\n')
        first = subprocess.Popen(["/bin/sh", str(WORKMUX), "locked"], env=self.env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        time.sleep(0.15)
        second = subprocess.Popen(["/bin/sh", str(WORKMUX), "locked"], env=self.env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        first.communicate(timeout=10)
        second.communicate(timeout=10)
        self.assertEqual(count.read_text().splitlines(), ["restore"])
        self.assertEqual(self.tmux("display-message", "-p", "-t", "locked:0.0", "#{pane_current_command}").stdout.strip(), "btop")


if __name__ == "__main__":
    unittest.main()
