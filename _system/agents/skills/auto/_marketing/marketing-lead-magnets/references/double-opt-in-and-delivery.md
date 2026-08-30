# Double opt-in and delivery

## Contract

```text
promotion URL with UTMs
  -> /freebie/<slug>
  -> signup plus explicit consent
  -> pending durable lead
  -> confirmation email with one-time token
  -> confirmation endpoint
  -> confirmationDestinationUrl
  -> /freebie/<slug>/download
  -> visible downloadUrl
  -> optional VSL or upsell
```

Use a custom destination page by default. Direct asset delivery remains acceptable for a genuinely simple offer. The confirmation endpoint should validate a single-purpose hashed token, record confirmation once, preserve delivery when a downstream email provider is temporarily unavailable, and redirect only to the configured destination.

Keep the acquisition slug stable in route, database, email, provider fields, analytics, and R2 key. Store first/current signup attribution with the lead. A post-confirmation destination may add fixed values such as `utm_source=confirmation_email`, `utm_medium=email`, and the stable offer campaign, but must not overwrite the original acquisition touch.

Never shorten the token-bearing URL. Promotion URLs may use `$marketing-manage-utm-tracking-links` when explicitly requested. Use `$infra-file-upload` for the actual asset, then store its returned public URL as `downloadUrl` on the destination page/config.

Test invalid, expired, and replayed tokens; provider failure; destination redirect; download action; consent copy; tenant/offer isolation; and analytics payloads. Email confirmation does not protect a public object: use signed or authenticated delivery when secrecy is a requirement.
