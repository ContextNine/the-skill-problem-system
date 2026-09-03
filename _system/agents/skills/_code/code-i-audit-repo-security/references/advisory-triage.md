# Advisory Triage

An advisory is a public vulnerability report for a package/version range. It usually includes affected versions, patched versions, severity, CVE/GHSA IDs, references, and dependency paths.

Do not equate "audit found it" with "the app is exploitable." Check:

- Is the vulnerable package in runtime dependencies or dev/build tooling?
- Does the application process attacker-controlled input through the vulnerable package?
- Is the vulnerable function or feature actually used?
- Is the path server-side, browser-side, local-only, CI-only, or test-only?
- Is a patched version available without major upgrade risk?
- Is the advisory recent or actively exploited?
- Does the package run install scripts or ship native binaries?

Common high-priority categories:

- Authentication/authorization bypass
- SSRF, RCE, command injection, unsafe archive extraction
- XSS in sanitizers/Markdown/HTML renderers
- XML parser/entity issues when parsing untrusted XML
- Prototype pollution in request/config/query handling paths
- HTTP client/proxy bypass issues in server-side request paths
- Build/install lifecycle scripts in transitive dependencies

When no patched version exists, propose one of:

- Remove or replace the dependency.
- Patch locally with `pnpm patch` or a repo patch file.
- Add a narrowly scoped mitigation in application code.
- Document a temporary ignore only with evidence of non-reachability.
