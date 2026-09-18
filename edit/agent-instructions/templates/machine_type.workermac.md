### Worker Mac

User-installed fleet commands live in `~/.local/bin`. Return worker results through {{ fleet.primary.display_name }} (`{{ fleet.primary.id }}`), the primary Mac using {{ fleet.primary.access.provider }} at `{{ fleet.primary.access.host }}`.

{% if fleet.machine.vault.enabled %}
This worker Mac participates in the Vault under its registered checkout policy. Follow the Vault instructions below before accessing it.
{% endif %}
