#!/usr/bin/env python3
"""Preview and remove proven-merged local branches without discarding work."""

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

PROTECTED = {
    "main",
    "master",
    "prod",
    "production",
    "develop",
    "development",
    "staging",
    "demo",
    "gh-pages",
}
SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    ".next",
    "dist",
    "build",
    ".cache",
    ".workspace-sync",
    "__pycache__",
    "vendor",
    "secrets",
    ".secrets",
    "keys",
    "tokens",
    ".env",
}
SHA = re.compile(r"^[0-9a-f]{40,64}$")


def command(*args, cwd=None, input_text=None, check=True):
    env = dict(
        os.environ,
        GIT_TERMINAL_PROMPT="0",
        GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=10",
    )
    result = subprocess.run(
        args,
        cwd=cwd,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    if check and result.returncode:
        # Remote URLs and provider errors may contain credentials. Keep reports value-free.
        raise RuntimeError(f"{args[0]} {args[1]} failed with exit {result.returncode}")
    return result


def git(path, *args, **kwargs):
    return command("git", *args, cwd=path, **kwargs)


def output(path, *args):
    return git(path, *args).stdout.strip()


def ancestor(path, a, b):
    return git(path, "merge-base", "--is-ancestor", a, b, check=False).returncode == 0


def protected(name, keep):
    return (
        name in PROTECTED
        or name in keep
        or name.startswith(("release/", "maintenance/"))
    )


def discover(root):
    seen = set()
    for base, dirs, _ in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.endswith(".app")]
        if not (Path(base) / ".git").exists():
            continue
        try:
            common = output(
                base, "rev-parse", "--path-format=absolute", "--git-common-dir"
            )
        except RuntimeError:
            continue
        if common not in seen:
            seen.add(common)
            yield Path(base).resolve()


def remote_info(path):
    remote = output(path, "config", "--get", "remote.origin.url")
    match = re.fullmatch(
        r"(?:git@github\.com:|https://github\.com/)([^/]+/[^/]+?)(?:\.git)?", remote
    )
    return hashlib.sha256(remote.encode()).hexdigest(), match.group(
        1
    ) if match else None


def default_branch(path):
    symbolic = git(
        path,
        "symbolic-ref",
        "--quiet",
        "--short",
        "refs/remotes/origin/HEAD",
        check=False,
    ).stdout.strip()
    if symbolic:
        if symbolic not in {"origin/main", "origin/master"}:
            raise RuntimeError("origin default branch is not main/master")
        return symbolic.split("/", 1)[1]
    candidates = [
        name
        for name in ("main", "master")
        if git(
            path,
            "show-ref",
            "--verify",
            "--quiet",
            "refs/remotes/origin/" + name,
            check=False,
        ).returncode
        == 0
    ]
    if len(candidates) != 1:
        raise RuntimeError("origin main/master is missing or ambiguous")
    return candidates[0]


def merged_prs(repo, cache):
    if not repo:
        return []
    if repo not in cache:
        try:
            result = command(
                "gh",
                "pr",
                "list",
                "--repo",
                repo,
                "--state",
                "merged",
                "--limit",
                "200",
                "--json",
                "number,baseRefName,headRefName,headRefOid,mergeCommit,mergedAt",
            )
            cache[repo] = json.loads(result.stdout)
        except (RuntimeError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
            cache[repo] = []
    return cache[repo]


def pr_proves_merge(path, branch, pr, default, target):
    merge = (pr.get("mergeCommit") or {}).get("oid", "")
    return (
        pr.get("headRefName") == branch["name"]
        and bool(SHA.fullmatch(pr.get("headRefOid", "")))
        and ancestor(path, branch["sha"], pr["headRefOid"])
        and pr.get("baseRefName") == default
        and bool(pr.get("mergedAt"))
        and bool(SHA.fullmatch(merge))
        and ancestor(path, merge, target)
    )


def preview(path, keep, cache):
    row = {"path": str(path), "eligible": [], "unproven": [], "keep": keep}
    try:
        raw = output(
            path,
            "for-each-ref",
            "--format=%(refname:short)\t%(objectname)",
            "refs/heads",
        )
        branches = [
            dict(zip(("name", "sha"), line.split("\t"))) for line in raw.splitlines()
        ]
        branches = [b for b in branches if not protected(b["name"], keep)]
        if not branches:
            row["note"] = "no feature branches"
            return row
        default = default_branch(path)
        fingerprint, repo = remote_info(path)
        target_ref = "refs/remotes/origin/" + default
        git(path, "fetch", "--no-tags", "origin", f"refs/heads/{default}:{target_ref}")
        target = output(path, "rev-parse", target_ref)
        row.update(
            default=default,
            target_ref=target_ref,
            target_sha=target,
            remote_fingerprint=fingerprint,
            github_repo=repo,
        )
        prs = None
        for branch in branches:
            if ancestor(path, branch["sha"], target):
                row["eligible"].append(branch)
                continue
            if prs is None:
                prs = merged_prs(repo, cache)
            for pr in prs:
                if (
                    pr.get("headRefName") != branch["name"]
                    or pr.get("baseRefName") != default
                ):
                    continue
                head = pr.get("headRefOid", "")
                if (
                    SHA.fullmatch(head)
                    and git(path, "cat-file", "-e", head, check=False).returncode != 0
                ):
                    try:
                        number = int(pr["number"])
                        git(
                            path,
                            "fetch",
                            "--no-tags",
                            "origin",
                            f"refs/pull/{number}/head",
                        )
                        if output(path, "rev-parse", "FETCH_HEAD") != head:
                            continue
                    except (RuntimeError, ValueError, subprocess.TimeoutExpired):
                        continue
            proof = next(
                (
                    pr
                    for pr in prs
                    if pr_proves_merge(path, branch, pr, default, target)
                ),
                None,
            )
            if proof:
                row["eligible"].append(dict(branch, pr=proof))
            else:
                row["unproven"].append(branch)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        row["error"] = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
    return row


def worktrees(path):
    raw = output(path, "worktree", "list", "--porcelain", "-z")
    result = []
    for block in raw.split("\0\0"):
        fields = dict(line.partition(" ")[::2] for line in block.split("\0") if line)
        if fields.get("worktree"):
            result.append(fields)
    return result


def assert_clean(path):
    if output(path, "status", "--porcelain=v1", "--untracked-files=normal"):
        raise RuntimeError("checked-out worktree has uncommitted files")
    for marker in (
        "MERGE_HEAD",
        "CHERRY_PICK_HEAD",
        "REVERT_HEAD",
        "rebase-merge",
        "rebase-apply",
        "index.lock",
    ):
        marker_path = Path(output(path, "rev-parse", "--git-path", marker))
        if not marker_path.is_absolute():
            marker_path = Path(path) / marker_path
        if marker_path.exists():
            raise RuntimeError("Git operation in progress")


def remove_branch(row, branch):
    path = row["path"]
    name, tip = branch["name"], branch["sha"]
    report = {"path": path, "branch": name, "sha": tip}
    try:
        if protected(name, row["keep"]) or not SHA.fullmatch(tip):
            raise RuntimeError("protected or invalid branch")
        ref = "refs/heads/" + name
        if output(path, "rev-parse", ref) != tip:
            raise RuntimeError("branch changed since preview")
        if output(path, "rev-parse", row["target_ref"]) != row["target_sha"]:
            raise RuntimeError("default changed since preview")
        if remote_info(path)[0] != row["remote_fingerprint"]:
            raise RuntimeError("origin changed since preview")
        if not ancestor(path, tip, row["target_sha"]) and not pr_proves_merge(
            path, branch, branch.get("pr", {}), row["default"], row["target_sha"]
        ):
            raise RuntimeError("merge not proven")
        trees = worktrees(path)
        for wt in trees:
            if wt.get("branch") != ref:
                continue
            wp = wt["worktree"]
            if "locked" in wt:
                raise RuntimeError("worktree locked")
            assert_clean(wp)
            if Path(wp).resolve() == Path(path).resolve():
                default = row["default"]
                if any(t.get("branch") == "refs/heads/" + default for t in trees):
                    raise RuntimeError("default checked out in another worktree")
                exists = (
                    git(
                        path,
                        "show-ref",
                        "--verify",
                        "--quiet",
                        "refs/heads/" + default,
                        check=False,
                    ).returncode
                    == 0
                )
                if exists and not ancestor(
                    path, "refs/heads/" + default, row["target_sha"]
                ):
                    raise RuntimeError("local default has unpushed commits")
                if exists:
                    git(wp, "switch", "--no-overwrite-ignore", default)
                else:
                    git(
                        wp,
                        "switch",
                        "--no-overwrite-ignore",
                        "--track",
                        "-c",
                        default,
                        "origin/" + default,
                    )
                git(
                    wp, "merge", "--no-overwrite-ignore", "--ff-only", row["target_ref"]
                )
                report["checkout"] = default
            else:
                git(
                    wp, "switch", "--no-overwrite-ignore", "--detach", row["target_sha"]
                )
                report["checkout"] = "detached at origin/" + row["default"]
            assert_clean(wp)
        if any(wt.get("branch") == ref for wt in worktrees(path)):
            raise RuntimeError("branch still checked out")
        # Compare-and-delete refuses a concurrent branch move. Verify the target
        # in the same transaction, including for squash/rebase merge proofs.
        transaction = f"start\nverify {row['target_ref']} {row['target_sha']}\ndelete {ref} {tip}\nprepare\ncommit\n"
        git(path, "update-ref", "--stdin", input_text=transaction)
        git(path, "config", "--remove-section", "branch." + name, check=False)
        report["result"] = "deleted"
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        report.update(
            result="kept",
            reason=str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__,
        )
    return report


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument(
        "--root", type=Path, help="Discover nested repositories under this Code root"
    )
    scope.add_argument("--repo", type=Path, help="One exact repository path")
    scope.add_argument(
        "--apply",
        type=Path,
        help="Apply a saved preview after rechecking merge and worktree state",
    )
    parser.add_argument(
        "--plan", type=Path, help="Write a preview for later application"
    )
    parser.add_argument(
        "--github-cache",
        type=Path,
        help="Optional merged-PR JSON keyed by owner/repo, queried on the controller",
    )
    parser.add_argument(
        "--keep", action="append", default=[], help="Protect an additional local branch"
    )
    args = parser.parse_args()
    if args.apply:
        data = json.loads(args.apply.read_text())
        if data.get("schema_version") != 1:
            parser.error("Unsupported plan schema")
        results = [
            remove_branch(row, branch)
            for row in data["repos"]
            if not row.get("error")
            for branch in row["eligible"]
        ]
        write_json(args.apply.with_name(args.apply.stem + "-results.json"), results)
        print(
            json.dumps(
                {
                    "deleted": sum(r["result"] == "deleted" for r in results),
                    "kept": [r for r in results if r["result"] == "kept"],
                },
                indent=2,
            )
        )
        return
    if not args.plan:
        parser.error("--plan is required for a preview")
    selected = (args.repo or args.root).expanduser().resolve()
    if not selected.is_dir():
        parser.error("Selected path does not exist")
    if args.repo and output(selected, "rev-parse", "--show-toplevel") != str(selected):
        parser.error("--repo must name the repository root")
    cache = json.loads(args.github_cache.read_text()) if args.github_cache else {}
    rows = [
        preview(path, args.keep, cache)
        for path in ([selected] if args.repo else discover(selected))
    ]
    write_json(args.plan, {"schema_version": 1, "repos": rows})
    print(
        json.dumps(
            {
                "repositories": len(rows),
                "eligible": sum(len(r["eligible"]) for r in rows),
                "unproven": sum(len(r["unproven"]) for r in rows),
                "errors": [
                    {"path": r["path"], "reason": r["error"]}
                    for r in rows
                    if r.get("error")
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
