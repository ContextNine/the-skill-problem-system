{% if fleet.machine.access.host %}
Access: {{ fleet.machine.access.provider }} at `{{ fleet.machine.access.host }}`.
{% endif %}

{% if fleet.peers %}
Connected machines:

{% for peer in fleet.peers %}
- {{ peer.display_name }} (`{{ peer.id }}`): {{ peer.role }} {{ peer.platform }}{% if peer.access.host %}, {{ peer.access.provider }} `{{ peer.access.host }}`{% endif %}.
{% endfor %}
{% endif %}

{% if fleet.machine.vnc.kind == "native-url" %}
For GUI inspection from {{ fleet.primary.display_name }}, return the Screen Sharing link [{{ fleet.machine.vnc.url }}]({{ fleet.machine.vnc.url }}).
{% endif %}
{% if fleet.machine.vnc.kind == "ssh-novnc" %}
For GUI inspection, ensure {{ fleet.primary.display_name }} has established and confirmed the SSH noVNC tunnel with `vault machine vnc {{ fleet.machine.id }}`, then return its actual clickable loopback URL.
{% if fleet.runtime.novnc_url %}
The last recorded tunnel URL is [{{ fleet.runtime.novnc_url }}]({{ fleet.runtime.novnc_url }}); confirm it before use.
{% else %}
A possible forwarded URL is [http://127.0.0.1:61152/vnc.html](http://127.0.0.1:61152/vnc.html); its port is only an example.
{% endif %}
{% endif %}
