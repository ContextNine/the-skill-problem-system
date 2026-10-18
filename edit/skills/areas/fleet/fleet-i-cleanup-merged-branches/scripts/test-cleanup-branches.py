#!/usr/bin/env python3
"""Exercise cleanup against real Git repositories, including linked worktrees."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HELPER = Path(__file__).with_name("cleanup-branches.py")


class CleanupIntegration(unittest.TestCase):
    def test_merged_branches_dirty_worktrees_and_concurrent_edits(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            origin, repo = root / "origin.git", root / "repo"
            subprocess.run(
                ["git", "init", "--bare", str(origin)], check=True, capture_output=True
            )
            subprocess.run(
                ["git", "init", "-b", "main", str(repo)],
                check=True,
                capture_output=True,
            )

            def git(*args):
                return subprocess.run(
                    ["git", "-C", str(repo), *args],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()

            git("config", "user.name", "Cleanup integration")
            git("config", "user.email", "cleanup@example.invalid")
            git("config", "commit.gpgsign", "false")
            git("config", "core.hooksPath", str(root / "no-hooks"))
            git(
                "remote",
                "add",
                "origin",
                "https://github.com/example/branch-cleanup.git",
            )
            git(
                "config",
                "url." + origin.as_uri() + ".insteadOf",
                "https://github.com/example/branch-cleanup.git",
            )

            def commit(filename):
                (repo / filename).write_text(filename)
                git("add", filename)
                git("commit", "-m", "feat: " + filename)
                return git("rev-parse", "HEAD")

            commit("base")
            git("switch", "-c", "merged")
            commit("merged")
            git("switch", "main")
            git("merge", "--ff-only", "merged")
            git("switch", "-c", "squashed")
            older_tip = commit("first")
            pr_head = commit("second")
            git("switch", "main")
            git("merge", "--squash", "squashed")
            git("commit", "-m", "feat: squash both changes")
            merge_sha = git("rev-parse", "HEAD")
            git("branch", "-f", "squashed", older_tip)
            git("branch", "stale")
            git("branch", "prod")
            git("branch", "custom-long-lived")
            git("branch", "linked")
            git("branch", "dirty")
            linked, dirty = root / "linked", root / "dirty"
            git("worktree", "add", str(linked), "linked")
            git("worktree", "add", str(dirty), "dirty")
            (dirty / "unfinished").write_text("keep this")
            git("switch", "-c", "unfinished")
            unfinished_tip = commit("unfinished")
            git("switch", "main")
            git("push", "origin", "main")
            git("remote", "set-head", "origin", "main")
            git("switch", "merged")

            cache = root / "prs.json"
            cache.write_text(
                json.dumps(
                    {
                        "example/branch-cleanup": [
                            {
                                "number": 7,
                                "baseRefName": "main",
                                "headRefName": "squashed",
                                "headRefOid": pr_head,
                                "mergeCommit": {"oid": merge_sha},
                                "mergedAt": "2026-01-01T00:00:00Z",
                            }
                        ]
                    }
                )
            )
            plan = root / "plan.json"
            subprocess.run(
                [
                    sys.executable,
                    str(HELPER),
                    "--repo",
                    str(repo),
                    "--github-cache",
                    str(cache),
                    "--keep",
                    "custom-long-lived",
                    "--plan",
                    str(plan),
                ],
                check=True,
                capture_output=True,
            )
            row = json.loads(plan.read_text())["repos"][0]
            self.assertEqual(
                {b["name"] for b in row["eligible"]},
                {"merged", "squashed", "stale", "linked", "dirty"},
            )
            self.assertEqual({b["name"] for b in row["unproven"]}, {"unfinished"})
            self.assertEqual(git("branch", "--show-current"), "merged")

            # A concurrent commit after the preview must survive application.
            git("switch", "stale")
            stale_tip = commit("concurrent")
            git("switch", "merged")
            subprocess.run(
                [sys.executable, str(HELPER), "--apply", str(plan)],
                check=True,
                capture_output=True,
            )
            results = json.loads(plan.with_name("plan-results.json").read_text())
            self.assertEqual(
                {r["branch"] for r in results if r["result"] == "deleted"},
                {"merged", "squashed", "linked"},
            )
            self.assertEqual(
                {r["branch"] for r in results if r["result"] == "kept"},
                {"dirty", "stale"},
            )
            self.assertEqual(git("branch", "--show-current"), "main")
            self.assertEqual(git("rev-parse", "unfinished"), unfinished_tip)
            self.assertEqual(git("rev-parse", "stale"), stale_tip)
            self.assertEqual((dirty / "unfinished").read_text(), "keep this")
            self.assertTrue(linked.is_dir())
            self.assertEqual(
                subprocess.run(
                    ["git", "-C", str(linked), "rev-parse", "HEAD"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip(),
                merge_sha,
            )
            self.assertEqual(git("rev-parse", "prod"), merge_sha)
            self.assertEqual(git("rev-parse", "custom-long-lived"), merge_sha)


if __name__ == "__main__":
    unittest.main()
