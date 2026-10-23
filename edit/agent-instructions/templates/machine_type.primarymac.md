### Primary Mac

User-installed fleet commands live in `~/.local/bin`; Homebrew may live in `/opt/homebrew/bin` or `/usr/local/bin` according to the machine registry. This machine owns fleet desired state and aggregate verified agent state.

{% for peer in fleet.peers %}
{% if peer.computer_use_project %}
Prefer `{{ peer.computer_use_project }}` on {{ peer.display_name }} (`{{ peer.id }}`) for extensive Computer Use instead of using this Mac.
{% endif %}
{% endfor %}
