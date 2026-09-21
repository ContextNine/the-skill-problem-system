Do not run Docker locally. Use the configured development K3s infrastructure for PostgreSQL, Redis, and other backing services.
{% if fleet.development_services.k3s_context %}
Use K3s context `{{ fleet.development_services.k3s_context }}`{% if fleet.development_services.namespace %} in namespace `{{ fleet.development_services.namespace }}`{% endif %}.{% if fleet.development_services.postgres_service %} PostgreSQL: `{{ fleet.development_services.postgres_service }}`.{% endif %}{% if fleet.development_services.redis_service %} Redis: `{{ fleet.development_services.redis_service }}`.{% endif %}
{% else %}
The development K3s context and service endpoints are not registered yet. Obtain the development configuration before connecting; do not substitute production services.
{% endif %}
