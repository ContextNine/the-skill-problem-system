#!/usr/bin/env python3
"""Detach a verified public clone and turn it into a fresh user repository."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


EXPECTED_ORIGINS = {
    "https://github.com/MDerman/the-skill-problem-system.git",
    "git@github.com:MDerman/the-skill-problem-system.git",
}


def run(args: list[str], root: Path) -> str:
    result = subprocess.run(args, cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def prepare(root: Path) -> None:
    root = root.expanduser().resolve()
    git_dir = root / ".git"
    if not root.is_dir() or not git_dir.exists():
        raise RuntimeError(f"target is not a Git clone: {root}")
    origin = run(["git", "remote", "get-url", "origin"], root)
    if origin not in EXPECTED_ORIGINS:
        raise RuntimeError(f"refusing to detach an unexpected origin: {origin}")
    remotes = run(["git", "remote"], root).splitlines()
    if remotes != ["origin"]:
        raise RuntimeError("refusing to detach a repository with additional remotes")
    if run(["git", "status", "--porcelain"], root):
        raise RuntimeError("refusing to detach a dirty public clone")
    shutil.rmtree(git_dir)
    run(["git", "init", "-b", "master"], root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path)
    args = parser.parse_args()
    prepare(args.repository)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
