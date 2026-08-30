---
name: code-audit-repo-security
description: Audit JavaScript/TypeScript repositories for known package vulnerabilities, risky dependency install behavior, package-manager pinning, lockfile supply-chain risk, and advisory triage. Use when asked to run pnpm/npm/yarn/bun audit checks, review dependency advisories, detect vulnerable or possibly compromised packages, harden package-manager security settings, configure Dependabot/dependency review, or summarize repo dependency risk.
---

# Code · Audit Repo Security

## Workflow

1. Inspect the repo first:
   - Identify package manager from `packageManager`, lockfiles, and workspace files.
   - Check dirty git state before editing.
   - Prefer read-only audit commands unless the user asks to fix or harden config.

2. Run the bundled audit helper from the repo root:

```bash
python3 "$(vault root)/_system/agents/skills/auto/_code/code-audit-repo-security/scripts/audit_repo_security.py" .
```

Use `--json` when machine-readable output is needed. Use `--include-dev` to include dev dependencies where the package manager supports that distinction.

3. Follow up with native tools when useful:
   - pnpm: `pnpm audit --prod --json`, `pnpm audit --audit-level high`, `pnpm approve-builds`
   - npm: `npm audit --omit=dev --json`, `npm audit signatures`
   - GitHub: Dependabot alerts, dependency graph, dependency review action, security advisories

4. Triage advisories by exploitability, not only count:
   - Prioritize runtime dependencies over dev-only tooling.
   - Prioritize reachable code paths, server-side parsing, auth, SSR, XML/HTML sanitization, crypto, archive extraction, HTTP clients, and build/install scripts.
   - Treat audit counts as noisy; report unique packages/advisories and dependency paths.
   - Say clearly when an advisory has no patched version, requires a direct dependency upgrade, or needs an override/resolution.

5. Explain trust boundaries:
   - Signatures verify package artifact integrity, not code safety.
   - Advisories are known public vulnerability reports, not proof that everything else is safe.
   - Approved builds limit install-time code execution; they do not make approved packages impossible to compromise.

## Hardening Checklist

For pnpm repos, prefer explicit policy in `pnpm-workspace.yaml` when compatible with the pinned pnpm version:

```yaml
minimumReleaseAge: 1440
minimumReleaseAgeStrict: true
minimumReleaseAgeIgnoreMissingTime: false
strictDepBuilds: true
verifyStoreIntegrity: true
```

Keep `onlyBuiltDependencies` / build approvals narrow. Do not approve install scripts without tracing why the package is present and whether it legitimately needs native/build work.

For GitHub repos, recommend:
   - `.github/dependabot.yml` for daily package checks.
   - `dependency-review-action` on pull requests with `fail-on-severity: high` or stricter.
   - Notifications for Dependabot/security alerts.

## Reporting

Use this output shape:

```text
Summary: pass/fail and package manager detected
Findings: critical/high advisories first, with package, path, patched version, link
Install risk: lifecycle/build approvals, unpinned managers, exotic lockfile sources
Notification setup: Dependabot/dependency review status
Limitations: what audit/signatures cannot prove
Next actions: minimal ordered remediation steps
```

If making changes, keep them scoped to package/security config unless the user asks to remediate vulnerabilities.

## References

Read `references/advisory-triage.md` when deciding whether an advisory is truly urgent, likely reachable, or acceptable to temporarily ignore.
