# Fleet preview

`fleet preview` shares loopback development servers through an authenticated public HTTPS route. It uses OpenSSH and frp's HTTP SSH gateway, so developer machines need no additional tunnel client.

```sh
fleet preview share 3001
fleet preview share 4005
fleet preview share 3001 --name graph
fleet preview list
fleet preview stop 3001
fleet preview stop --all
```

Run these on the machine hosting the development server. The server must already listen on `127.0.0.1:<port>`. Sharing does not start it or change its port. Each preview has an independent SSH process. Sharing an active matching name reuses it; a conflicting name fails without replacing the existing session. `stop` closes all previews of the specified local port and leaves the application running.

Commands accept `--json`. `share --dry-run` returns the proposed command without opening a tunnel. The printed URL confirms SSH registration. Verify the public HTTPS authentication gate and an authorised application response before describing the URL as ready.

## Configuration

Resolve the editable package with `fleet source path`. Its `./edit/settings/fleet/preview.json` owns non-secret instance configuration. The installed copy lives under `fleet config path`. Keep it disabled until the public relay, certificate and authentication policy are accepted. Settings contain public names and key paths, never private keys or passwords.

```json
{
  "schema_version": 1,
  "enabled": true,
  "domain": "preview.example.com",
  "hostname_prefix": "",
  "relay_host": "fleet-preview.fleet-preview.svc.cluster.local",
  "relay_port": 2200,
  "identity_file": "~/.ssh/fleet_preview_ed25519",
  "host_key": "ssh-ed25519 <public relay key>",
  "viewer_authentication": "required"
}
```

The default public name is `<registered-machine>-<local-port>.<domain>`. An optional `--name graph` replaces the port in that name. `hostname_prefix` supports a flat scheme such as `preview-worker-3001.example.com` with domain `example.com` and prefix `preview-`. Confirm certificate coverage for the chosen names before enabling them. Normal Cloudflare Universal SSL on a full zone covers one subdomain level; nested preview names need matching certificate coverage.

`identity_file` is optional when the registered machine already has `fleet_shell.identity_file`; an explicit preview value overrides that path. The command consumes the key through OpenSSH and never reads it into session state. On macOS, OpenSSH uses the existing Keychain passphrase for that identity, including in an SSH shell without an agent socket.

The private relay must authenticate SSH clients through a non-empty authorised public-key file. Provision the relay host key durably. Obtain its public key through authenticated infrastructure administration, save the public type and base64 data in `host_key`, and enrol only approved fleet public keys. Do not use unchecked key scanning, automatic host acceptance, inline tokens, or credentials in command arguments. The command pins the configured host key in a session-specific known-hosts file.

The relay is a private Kubernetes Service reached through the fleet's VPN routes. Viewer authentication and public TLS live at the shared public routing layer. The shared ingress requires HTTP basic authentication on every generated hostname. HTTP must redirect to HTTPS before the password prompt. Retrieve the shared passcode from Notenv Personal Globals as `FLEET_PREVIEW_PASSWORD`; the login username is `preview`. No email allowlist is required. An application login alone is not the preview authentication gate.

## Session lifetime and troubleshooting

Machine-local records and logs live under `~/.agents/state/previews/` with user-only permissions. `list` reports running, stopped or failed sessions. Inspect the recorded `.log` when registration fails. SSH connection failures end the preview; there is no silent fallback or automatic restart loop.

- No local listener: start the intended server on a free loopback port first.
- SSH timeout: check the private relay Service, VPN and enrolled key.
- Host verification failure: investigate relay identity; replace the public pin only after an authorised key change.
- Duplicate proxy name or hostname: keep the existing preview or choose another label.
- Public TLS failure: verify DNS and edge certificate coverage.
- Public 502: check the relay, tunnel and local server.
- Hot reload or origin rejection: check the app's development origin allowlist. The HTTP relay carries WebSockets without path rewriting.

After changing the owning source, validate and apply Fleet skill sync. Runtime changes use the managed Fleet installer. Do not hand-edit generated skill snapshots or install separate copies of the command.
