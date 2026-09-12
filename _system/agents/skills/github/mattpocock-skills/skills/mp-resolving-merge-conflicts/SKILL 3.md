---
description: Use when you need to resolve an in-progress git merge/rebase conflict.
metadata:
    github-path: skills/engineering/resolving-merge-conflicts
    github-ref: refs/tags/v1.2.3
    github-repo: https://github.com/mattpocock/skills
    github-tree-sha: 6aa1ed0b40fac0ebea5c0cf6f2addf82c99b6323
name: mp-resolving-merge-conflicts
---
1. **See the current state** of the merge/rebase. Check git history, and the conflicting files.

2. **Find the primary sources** for each conflict. Understand deeply why each change was made, and what the original intent was. Read the commit messages, check the PRs, check original issues/tickets.

3. **Resolve each hunk.** Preserve both intents where possible. Where incompatible, pick the one matching the merge's stated goal and note the trade-off. Do **not** invent new behaviour. Always resolve; never `--abort`.

4. Discover the project's **automated checks** and run them — typically typecheck, then tests, then format. Fix anything the merge broke.

5. **Finish the merge/rebase.** Stage everything and commit. If rebasing, continue the rebase process until all commits are rebased.
