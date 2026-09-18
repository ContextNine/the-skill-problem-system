## Playwright CLI

Dependency ID: `playwright-cli`; optional Linux idle cleanup is `playwright-cli-watchdog`. The CLI is selected for browser-automation machines and consumed by `code-i-playwright-cli`. Node 24 is its approved prerequisite.

Install the approved `@playwright/cli` channel into the managed user-local npm prefix, then verify `playwright-cli --version`. Browser downloads are explicit and use Playwright's own browser management; they are not inferred from skill discovery. The watchdog is a separate optional systemd user service and wrapper, never an implicit consequence of installing the CLI.

Updates preserve the managed prefix and re-run a real browser launch smoke test. Recovery restores the previous package version and wrapper ownership. Do not remove browser caches, traces, or user profiles without a separate request.
