# Platform runtime

Use the registered machine facts and the command paths discovered by the workflow. Do not infer a different platform, role, home, Code root, or Vault participation.

{% include "templates/platform-runtime.md" %}

Selected machine: {{ fleet.machine.display_name }} (`{{ fleet.machine.id }}`), a {{ fleet.machine.role }} on {{ fleet.machine.platform }}. Its Code root is `{{ fleet.machine.roots.code }}` and Vault participation is `{{ fleet.machine.vault.checkout_mode }}`.
