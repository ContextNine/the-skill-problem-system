---
name: fleet-i-public-dev-preview
description: Use when asked to preview or show public dev preview for a given dev server.
---

# Public development previews

Use `fleet preview` to share an already running development server through the configured private SSH relay and authenticated public HTTPS route. Local loopback previews remain the default unless the user asks to share publicly.

Read `./references/preview.md` for setup and troubleshooting. Resolve the editable Fleet source with `fleet source path`. Changing relay infrastructure requires `$k3s-infrastructure-kubernetes`; resolve its checkout with `$fleet-i-code-folder-and-computer-topology`. Never rewrite the shared routing configuration from an application repository.

## Choose the server and port

- Inspect the application's start command and active listeners. Select the port where the requested server is actually running. Do not assume port 3000, publish every listener, or change another application's port.
- If starting the requested server, bind it to `127.0.0.1`. Prefer the application's normal port when free; otherwise choose a free local port and report the mapping. Check both the listener and an HTTP response before sharing.
- Run the command on the machine hosting the server. Registered machine identity and local port determine the public name, so identical ports on different machines can coexist. The relay handles forwarding allocation; there is no public port to reserve.
- Reuse an active matching preview. A name collision or failed SSH registration is a failure, not permission to replace another preview or bypass authentication.

```sh
fleet preview share <actual-port>
fleet preview list
fleet preview stop <actual-port>
```

Use `--name <label>` on `share` when a descriptive label is useful. `--dry-run` shows the proposed mapping without opening a tunnel. `--json` returns structured session state. Multiple `share` commands can run simultaneously.

## Verify and return

SSH registration proves the forwarding session exists. Before reporting a public preview as ready, verify HTTPS, rejection or a login redirect for unauthenticated visitors, and an authorised browser loading the expected application. Preserve WebSocket forwarding for hot reload. Configure the application's allowed development origin or callback URL only if its actual behaviour requires it.

Return the exact clickable URL printed by the command and identify the source machine and local port. Keep the development server and sharing session alive while useful. If sharing fails, inspect its recorded log and confirm the previous process and children have exited before retrying. Never disable strict host verification or viewer authentication to make a preview work.

`stop` closes sharing and leaves the development server running. Stop only the requested port; use `stop --all` only when the user asks to close all this machine's previews. Public URLs stop serving the app when their tunnel closes or the source machine sleeps.

If configuration is missing or disabled, complete the setup in the owning source documentation before claiming public access. Use `$notenv-cli` for protected provider values. Do not inspect plaintext credentials or create an unauthenticated fallback route.
