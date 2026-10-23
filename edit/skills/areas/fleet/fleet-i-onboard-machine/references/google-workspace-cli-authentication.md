# Google Workspace CLI Authentication

This reference owns the intended `gws` authentication grant for every registered machine and every Vault workflow. Role-specific onboarding and service skills must point here instead of defining narrower login commands.

## Intended everyday grant

Use this complete service set for initial login and every reauthorization:

```bash
gws auth login --services gmail,calendar,drive,sheets,docs,slides,tasks
```

The grant covers Gmail, Calendar, Drive, Sheets, Docs, Slides, and Tasks. `gws auth login` replaces the stored grant, so a later login with fewer services can remove access that another workflow relies on. Never reauthorize with a reduced service list.

## Decision path

1. Start with `gws auth status`.
2. If credentials are valid, run the requested command. Do not log in again as routine setup.
3. Run `gws auth setup` only when the machine has no OAuth client configuration.
4. Run the canonical login only when credentials are missing, a service was added to the canonical grant, or Google returns an authentication or insufficient-scope error.
5. After authentication work, prove the requested service with a harmless read.

If status is valid but a service still returns `401` or `403`, move the disposable `token_cache.json` from the GWS config directory to Trash and retry the harmless read. Keep the encrypted credentials file intact. Run the canonical login only if the retry still shows missing or insufficient authorization.

OAuth credentials and tokens remain machine-local. A working login on one machine does not enroll another machine.
