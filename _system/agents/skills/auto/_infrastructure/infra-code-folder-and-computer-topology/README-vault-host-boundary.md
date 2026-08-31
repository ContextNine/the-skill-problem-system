## Vault Host Boundary

Vault reads and writes run only from one of three schema-v7 registered full-worktree modes:

- `primary-external-git`: the one iCloud Mac and Vault Git owner;
- `icloud-gitless`: a complete Keep Downloaded iCloud worker Mac;
- `remote-sshfs`: a Linux SSH worker whose machine-local client proves the exact registered Mac source and a healthy full mount.

A host in mode `none`, an arbitrary path, retired clone, sparse checkout, missing or wrong-source mount, read-only mount, unresolved identity, dataless/conflicted host, or unknown health state is not a Vault host.

### Remote client gate

On a registered `remote-sshfs` machine, the installed launcher works while the mount is absent. Before any task-specific read:

```sh
vault access status
cd "$(vault root)"
```

Status must prove SSH, exact `fuse.sshfs` source, read-write mount, sentinel, registered host identity, Keep Downloaded and recursive materialization, current downloaded state, and no conflict or pause. Pending outbound upload and a container that is not caught up do not block access. Before managed writes, close unmanaged Vault writers and run `vault access begin`; finish with `vault access finish`.

Never use mount failure as permission to create a clone, sparse checkout, copied publication tree, or broader home mount. Setup and recovery belong to [[linux-remote-vault-access|Linux Remote Vault Access]] through `$infra-onboard-machine`.

### Non-participating hard stop

When the current machine is not one of the three valid modes, stop before reading the requested Vault note, running task-specific Vault commands, inspecting Vault Git, or following Vault links.

Do not:

- message, reuse, fork, create, hand off to, wait for, or poll another task;
- remain active as a coordinator;
- use SSH to make the primary publish or execute the Vault task;
- fetch, repair, recreate, mount, or use an unregistered Vault path.

Return one concise instruction:

> This Vault task was launched on a non-Vault host. Run it in a registered full Vault worktree. For code execution, run the repository-local plan from the owning worker code project.

This is terminal for that task. Do not retry automatically.

### Executable plans

Long-running build, deployment, or repository plans intended for a Code worker keep a self-contained copy in the owning repository with every binding required for execution. The repository copy is the worker entrypoint; the Vault copy is planning context and names that repository path and invocation.

Code-only workers record proposed Vault-facing updates in a repository evidence packet. A separately launched registered Vault task may apply it later. Neither task waits for or polls the other.
