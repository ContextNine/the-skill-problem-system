### Worker Mac with low memory

User-installed fleet commands live in `~/.local/bin`. Return worker results through {{ fleet.primary.display_name }} (`{{ fleet.primary.id }}`), the primary Mac using {{ fleet.primary.access.provider }} at `{{ fleet.primary.access.host }}`.

Keep local development workloads small and use the configured development K3s services instead of starting local containers.

{% if fleet.machine.vault.enabled %}
This worker Mac participates in the Vault under its registered checkout policy. Follow the Vault instructions below before accessing it.
{% endif %}
