## Linux worker image

Dependency ID: `linux-worker-image`. The `codex-machine-image` workspace owns boot-critical Ubuntu image packages and exact versions in its `image.lock`; `dependencies.json` owns the fleet acceptance identity. This replaces the former parallel Linux dependency YAML.

The image contract supplies OpenSSH, Git/Git LFS, GitHub CLI, curl, jq, Python, ripgrep, rsync, archive tools, Node/npm/pnpm, Secret Service support, tmux, btop, and Starship, plus required SSH and D-Bus services. Direct agent packages may intentionally verify or install overlapping commands because the distributed agent package must remain standalone.

Coding tools, access providers, optional project tools, and authentication are separate dependency entries. Image rebuilds verify the declared command/service contract and owning image lock before fleet acceptance. Major OS upgrades, image publication, and production rollout require separate authorization.
