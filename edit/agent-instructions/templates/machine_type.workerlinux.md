### Linux worker

User-installed fleet commands and portable skill snapshots live below the home directory. The Codex Browser plugin runtime is unavailable here. Use `playwright-cli` for development-server browser work, including sign-in to development accounts.

{% for peer in fleet.peers %}
{% if peer.computer_use_project %}
For personal or business account sessions, such as Gmail or App Store Connect, create a Codex task in `{{ peer.computer_use_project }}` on {{ peer.display_name }} (`{{ peer.id }}`) and use its logged-in browser. Keep this task as coordinator and wait for it. Do not hand off this task or use ChatGPT Work cloud.
{% endif %}
{% endfor %}

Return worker results through {{ fleet.primary.display_name }} (`{{ fleet.primary.id }}`), the primary Mac using {{ fleet.primary.access.provider }} at `{{ fleet.primary.access.host }}`.
