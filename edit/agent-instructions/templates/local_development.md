Do not run Docker locally. Use the configured development K3s infrastructure for PostgreSQL, Redis, and other backing services.
Resolve the current repository's non-secret `development` target from the fleet workspace registry before connecting. Each application owns its `local` namespace and database identity. Do not substitute staging or production services.
