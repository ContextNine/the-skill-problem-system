# Development previews

• When working on a registered worker, proactively expose a useful localhost-inspectable preview to Matt when the changes would benefit from inspection and the request did not instruct you to commit immediately or to commit and push.
• Bind the development server to worker loopback `{worker_loopback}`. From the worker, open an SSH reverse port forward to the registered primary's canonical alias, `{primary_ssh_alias}`, with the listener bound only to primary loopback `{primary_loopback}`: `ssh -NT -o ExitOnForwardFailure=yes -R {primary_loopback}:{primary_port}:{worker_loopback}:{worker_port} {primary_ssh_alias}`.
• Use the same port on both ends when available. Never apply a fixed port offset. If that port is unavailable on the primary, choose any free primary loopback port and report the exact mapping.
• Return the clickable `http://{primary_loopback}:{primary_port}` URL and keep the development server and tunnel alive while the preview remains useful. Never bind the preview listener to a LAN or mesh address.
