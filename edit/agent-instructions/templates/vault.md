{% if fleet.machine.vault.enabled %}
Vault root: `{{ fleet.machine.roots.vault }}`.

{% if fleet.machine.vault.checkout_mode == "primary-external-git" %}
This machine is the sole Vault Git and fleet owner. Edit the local Vault normally. Commit and push the complete worktree currently visible here without waiting for iCloud upload.
{% endif %}
{% if fleet.machine.vault.checkout_mode == "icloud-gitless" %}
This is a full, Keep Downloaded iCloud worktree with deliberately unresolved Git metadata. Edit the local Vault normally. Never run Vault Git, refresh, release, agents sync, or Git-backed media maintenance here.
{% if fleet.machine.vault.remote_access.host_enabled %}
It is the registered iCloud worktree host for remote clients.
{% endif %}
{% endif %}
{% if fleet.machine.vault.checkout_mode == "remote-sshfs" %}
This is a registered full read-write remote Vault client. `{{ fleet.machine.roots.vault }}` mounts the complete iCloud worktree from {{ fleet.vault_source.display_name }} (`{{ fleet.vault_source.id }}`) through the stable SSH alias `{{ fleet.vault_source.ssh_alias }}` at `{{ fleet.vault_source.roots.vault }}`. Before reading or editing the Vault, run `vault access status`. Continue only when it succeeds and reports `"ok": true`; otherwise do not edit. An absent, read-only, wrong-source, or unhealthy mount is a hard stop, never a reason to recreate a clone or sparse checkout. Vault Git, refresh, release, agents sync, bootstrap publication, and Git-backed media maintenance are prohibited here. Git remains fully available in ordinary Code repositories. Only the registered Vault Git owner may report `git-pushed`.
{% endif %}
{% endif %}
