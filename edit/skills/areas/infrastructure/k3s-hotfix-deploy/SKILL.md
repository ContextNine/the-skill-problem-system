---
name: k3s-hotfix-deploy
description: Use when the user asks to commit, push, release, deploy, or verify a proven production hotfix for a registered repository.
---

# Deploy a hotfix

This skill is the shared release boundary. It does not diagnose errors and does not publish Impression browser extensions.

1. Run the preflight and use its resolved repository record:

   ```bash
   python3 "./scripts/hotfix.py" preflight --repository <workspace-id>
   ```

2. Compose `$fleet-i-code-folder-and-computer-topology` and use the existing checkout. Capture the preflight's initial changes. Preserve unrelated work, stage only the repair, and recheck for concurrent edits before committing. Never clone, create worktrees, stash, reset or clean. Stop on overlapping work or unsafe upstream integration. Run the record's focused verification plus the smallest regression check.
3. Commit with `hotfix: <summary>`, push `master`, and record the exact SHA. Never add `hotfix:` to an ordinary agent commit.
4. Observe the repository's `Release` workflow or established GitLab exact-commit release. Use `gh` directly, never a package-manager wrapper.
5. Verify that the exact SHA and immutable image reached production, then run the configured health and rollout checks.
6. If Impression verification fails, use its supported prior-compatible release rollback and verify recovery. For every other repository, stop and report the preserved prior healthy release without applying it.
7. Return exact commit, GitHub run, GitLab pipeline, digest, deployment, and verification identifiers when available.

Never bypass checks, signing, environment-contract validation, serialization, or health verification because a commit is a hotfix.

The workflow observer reports CI completion, not proof of production deployment. Independently verify the exact live release. Infrastructure, delivery-template and shared-package changes use their owning documented operation, not an application release policy. Record each changed repository separately.
