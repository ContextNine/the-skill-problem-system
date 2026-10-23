---
type: agent-reference
status: enabled
---

## Machine-local secrets and enrollment

Config paths beginning with `./fleet/`, `./skills/`, or `./dependencies/` are relative to the directory returned by `fleet config path`.

Paths beginning with `./internal/` are relative to the package returned by `fleet source path`.

Start with `./machine-local-secrets.md` for package-level ownership and focused credential references.

`./fleet/machine-secrets.json` is the canonical non-secret vocabulary and routing registry. It says what each credential is for, where its protected custody lives, whether it is generated, reissued, guarded-copy, interactive, or service-only, and which exact enrollment and verification procedure owns it. It never contains a private value or a registry of desired private state.

`./internal/generated/state/machine-secrets.lock.json` contains only sanitized facts emitted after verification: machine ID, credential name and provider ID where public, expiry, scopes, custody kind, helper digest, and boolean acceptance. An absent entry means unverified, not absent. Never hand-edit a successful record or infer it from file presence.

Every credential entry must include a non-secret `documentation` reference that resolves either inside the agent package, to a manual skill reference, or through a logical workspace ID plus repository-relative path. Repository-owned authorities likewise use logical workspace IDs instead of checkout paths. Resolve those IDs through `fleet config` and schema-v3 `fleet/workspaces.json`; never persist expanded paths as authority.

Keep the lifecycle classes in this one registry rather than splitting them into separate manifests. The class answers the bootstrap question directly:

| Class | Created where | Machine setup behavior |
| --- | --- | --- |
| `generated` | Target machine | Create a new private identity locally; distribute public material only |
| `reissued` | Provider or primary authority, uniquely for target | Deliver once into target-native custody; replace rather than copy or recover |
| `guarded-copy` | Reviewed authority machine | Copy only through the named guarded script with digest, permission, conflict, and acceptance checks |
| `interactive` | Target machine | Repeat login, consent, MFA, passkey, or OS approval locally |
| `service-only` | Provider, CI, cluster, or service | Never enroll into fleet user accounts |

Separate files would make lifecycle changes and cross-class audits harder and create duplicate IDs. Consumers may filter this registry by `class`, `machines`, or `purpose` when producing an onboarding checklist.

### Custody rules

- Generate machine identities on their target. Copy only public keys or recipients to providers.
- Reissue revocable machine tokens from their owning authority. Deliver a new target-specific value once through authenticated SSH directly into Keychain or Secret Service, verify it on the target, then revoke the replaced token.
- Copy portable authority only through its owning guarded enrollment script. The script must identify source and target, avoid content output, preserve a conflicting target before reviewed replacement, enforce permissions, compare safe digests or public derivations, and perform a real acceptance check.
- Recreate OAuth, passkey, app, and provider sessions through target-local protected interaction.
- Keep CI, Kubernetes service, database, deployment, and object-storage credentials in provider or service custody. They are not machine onboarding material.

### Current deterministic routes

| Authority | Route | Acceptance |
| --- | --- | --- |
| GitHub Git SSH | `github_fleet_auth.py` | Dedicated target public key enrolled; exact SSH transport passes |
| GitHub CLI OAuth | `gh auth login --web --git-protocol ssh` | API auth passes and no plaintext fallback exists |
| Shared SOPS Age | `enroll_sops_key.py` | Recipient/digest, permissions, and repository decrypt pass |
| Kubernetes operator kubeconfig | `./kubernetes-operator-kubeconfig.md` | Digest, mode, context, and read-only namespace query pass |
| ctx9 GitLab reads | `setup-fleet-read-credential.sh` in `ctx9/delivery` | Exact group scopes, native custody, package read, and sanitized lock record pass |
| Notenv identities | Notenv fleet installer | Unique channel, Age, and unlock identities plus broker acceptance pass |
| Langfuse coding-agent API | `$fleet-configure-langfuse-coding-agents` | Plugins remain disabled without credentials; after target-specific enrollment, two harmless test turns and exact trace/usage lookup pass |
| Claude provider API keys | `$code-i-use-claude-code-proxy-or-openrouter` | Native credential status plus one bounded live route and tool-use check pass |
| Rclone Google Drive OAuth | `$fleet-i-manage-rclone-google-drive` target-local configure flow | Exact `drive.file` policy, encrypted config, live dedicated-root read, and random sentinel round trip pass |
| Rclone config unlock | Target-local generation into Keychain or Secret Service | `rclone config encryption check` passes only through the absolute password command |
| Google OAuth desktop-client secret | Reviewed guarded enrollment into target-native custody | Desired client ID matches, no client secret persists in Rclone config, and target-local OAuth passes |
| CodeFolderSync backup age | `codefoldersync_backup_age.py` through `./codefoldersync-backup-age-recovery.md` | Both recovery machines decrypt the same generated non-secret fixture; only public recipients are distributed |
| WireGuard or Tailscale | Selected provider onboarding route | Provider status and a new inbound SSH connection pass |

The SOPS identity is an explicit guarded portable fleet authority retained for repositories that still need it. It is different from Notenv' generated, nonportable machine Age identity. Kubeconfig is likewise an explicit operator capability, never an automatic all-machine secret.

### CodeFolderSync Google Drive backup boundary

Selected backup machines are not accepted merely because Rclone is installed. Preview and approve the direct dependency through `$fleet-i-update-dependencies`, then enroll the two native Rclone records through this onboarding workflow. Generate the config unlock independently on the target. Enroll the reviewed OAuth desktop-client secret as guarded application authority without writing it to a file, shell profile, process argument, or Rclone configuration.

Each machine must then complete OAuth locally through `$fleet-i-manage-rclone-google-drive`. Reboot acceptance re-runs encrypted configuration verification and a read-only dedicated-root check; it does not create another sentinel or upload a real archive. Revocation disables uploads, proves retained-backup recovery, revokes that target's OAuth grant, and removes its native records without deleting Drive snapshots. The configured recovery machines generate independent age identities; backup sources receive only their public recipients.

### ctx9 GitLab read credential

The broader GitLab management token is protected Delivery operator authority in the environment-scoped Personal Global. It is not a fleet-machine credential and has no Keychain or Secret Service fallback. Delivery's `local-admin` profile verifies its process-scoped GitLab identity and group inventory without returning the value.

Where private GitLab packages are configured, each eligible machine receives its own revocable group-read credential with the scopes declared by the owning repository. Resolve the group, projects, and credential name from installed configuration. Do not assume a particular organization or grant write or API access merely to read packages.

The primary runs the GitLab automation controller with the Notenv helper source and a state-output path. Preview first even though apply is the controller default:

```bash
DELIVERY_REPO="$HOME/Code/ctx9/delivery"
NOTENV_HELPER="$HOME/Code/ctx9/notenv/scripts/private-read.py"
STATE="$(fleet source path)/internal/generated/state/machine-secrets.lock.json"
ADMIN_RUNNER="$(mktemp -d)"
trap 'rm -rf -- "$ADMIN_RUNNER"' EXIT
cp "$DELIVERY_REPO/.env.base" "$ADMIN_RUNNER/.env.base"

(cd "$ADMIN_RUNNER" && notenv exec --globals --environment local --contract .env.base -- \
  "$DELIVERY_REPO/setup-fleet-read-credential.sh" dry-run \
    --machine-id <machine-id> --platform <macos|linux> --host <local|ssh-alias> \
    --helper "$NOTENV_HELPER" --state-output "$STATE" --json)

(cd "$ADMIN_RUNNER" && notenv exec --globals --environment local --contract .env.base -- \
  "$DELIVERY_REPO/setup-fleet-read-credential.sh" \
    --machine-id <machine-id> --platform <macos|linux> --host <local|ssh-alias> \
    --helper "$NOTENV_HELPER" --state-output "$STATE" --json)
```

The controller installs only reviewed helper code, creates a target-specific token in memory, sends its enrollment payload over authenticated SSH stdin, and stores the value natively. It verifies real private-package access before replacing target metadata and revokes the old machine-named token only after the replacement passes. No token is returned in output.

On a remote Mac, Keychain enrollment and verification run as a disposable job in the logged-in user's GUI bootstrap domain because the SSH audit session is intentionally denied protected Keychain operations. The payload travels from authenticated SSH stdin through a mode-`0600` FIFO directly into the helper; it never enters a file or process argument. The controller captures only sanitized helper status and removes the FIFO, output files, and job after completion. Workspace-backed installers that consume the credential use the same GUI-domain boundary.

Use the credential without a plaintext npmrc, Docker config, Git remote, or shell export:

```bash
ctx9 auth verify --json
ctx9 auth exec -- pnpm install --frozen-lockfile
ctx9 auth exec -- git ls-remote https://gitlab.com/ctx9/notenv.git
ctx9 auth exec -- docker pull registry.gitlab.com/ctx9/<project>/<image>:<tag>
```

The wrapper injects npm, Git credential-helper, and Docker credential-helper configuration only for the child process. The token remains in native storage and process memory and is not written to the temporary configuration files.

The helper source and deterministic credential-free bootstrap archive are owned by `ctx9/notenv`.
Onboarding may install the helper before Notenv itself, then enroll the per-machine token as a
separate operation. Software presence, native enrollment, package verification, and later Notenv
broker readiness are distinct states.

### Notenv boundary

Notenv models provider-owned custody: Keychain, Secret Service, SOPS, SSH agent, CI, and service stores remain the authorities, and plaintext fallback is forbidden. Notenv generates and protects its own machine identities and consumes referenced provider values in broker or child-process memory.

Notenv intentionally does not manufacture GitHub OAuth, VPN identity, kubeconfig, shared SOPS authority, or other providers' credentials. Those are prerequisites owned by fleet onboarding. The GitLab read credential closes the bootstrap loop for Notenv' private npm packages: onboarding enrolls it first, then the Notenv installer uses `ctx9 auth exec` for its frozen dependency install. Notenv records the service standard but never absorbs the token into its own portable state.

The generated Notenv identity registry ID is `notenv-machine-identities`. Native custody
uses only the `notenv-*` service/provider names above; no retired alias exists. Recovery generates a
new target-local identity, enrolls its public material, and retires the prior identity without copying private
material between machines.

### Langfuse coding-agent boundary

Use `$fleet-configure-langfuse-coding-agents` for official observability plugins and separate authenticated Langfuse API access. Codex uses target-specific keys in local `~/.codex/langfuse.json` with mode 0600, explicitly approved on 2026-10-10 and excluded from Git and fleet sync. The official exporter loads it directly; do not install a custom launcher or native credential adapter. Claude retains its native plugin configurator. Follow the Langfuse skill for exact hook review, harmless two-turn server verification and separate desktop acceptance. Replacing functionality includes removal of superseded hooks, code, state and native credential items, followed by revocation of old keys after replacement acceptance. Never synchronize project keys or authenticated MCP headers.

Langfuse credentials are `reissued`: create an independently revocable project-scoped pair for each selected machine, enroll it in the selected integration's documented custody, prove two harmless turns and exact trace/usage lookup, then revoke the replaced pair. Absence from `machine-secrets.lock.json` means the integration is not accepted even when a plugin or local configuration is present.
