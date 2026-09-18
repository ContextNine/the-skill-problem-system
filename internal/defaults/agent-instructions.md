# Agent instructions

Follow the project instructions and the machine-specific guidance below.

***

## Machine

{{ fleet.machine.display_name }}. Code root: `{{ fleet.machine.roots.code }}`.

{% include "templates/machine_type.md" %}

{% include "templates/vault.md" %}

{% include "templates/connections.md" %}

***

## Local development

{% include "templates/local_development.md" %}

{% if fleet.machine.role == "worker" %}
{% if fleet.peers %}
{% include "templates/development-previews.md" %}
{% endif %}
{% endif %}
