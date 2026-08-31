# API and Automation

## Control planes

Use Google Analytics Admin API for GA4 configuration and Tag Manager API v2 for GTM resources. Google Workspace CLI does not own these marketing products.

The bundled `scripts/google-marketing.mjs` supports:

- `validate`: validate required manifest identifiers.
- `hash`: SHA-256 an immutable export.
- `snapshot`: read GA4 property/stream/retention/enhanced measurement/custom definitions/key events and GTM account/container/live version.
- `diff`: compare the normalized snapshot with desired names, URL, and retention.
- `apply`: rename supported GA4/GTM resources, set 14-month retention, and create missing configured custom dimensions/key events.
- `publish`: publish one explicit existing GTM container version.

Mutation commands are dry-run by default and print the exact confirmation string required with `--execute`.

## Authentication

Use user Application Default Credentials with the least scopes needed for the operation. The script obtains a token in memory with `gcloud auth application-default print-access-token` and never prints it. Keep OAuth client downloads and the ADC file outside Git.

Read-only work needs Analytics and Tag Manager read scopes. Apply/publish additionally need Analytics Edit and the relevant Tag Manager account/container edit and publish scopes. Enable the Analytics Admin API and Tag Manager API in the selected Google Cloud project.

## Coverage rule

Do not imply that one API snapshot captures every UI surface. Record UI-only settings, consent diagnostics, access recovery, and Tag Assistant evidence alongside API output. If an API operation fails because a field is alpha-only or permissions are insufficient, use the signed-in UI, then read back and snapshot.

Primary references:

- https://developers.google.com/analytics/devguides/config/admin/v1
- https://developers.google.com/tag-platform/tag-manager/api/reference/rest
- https://developers.google.com/tag-platform/tag-manager/api/v2/authorization
