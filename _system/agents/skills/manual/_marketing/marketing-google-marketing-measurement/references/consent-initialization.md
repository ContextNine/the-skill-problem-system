# Consent Initialization

## Ownership

- The application/CMP owns the UI, persistence, and the visitor's explicit choice.
- A GTM custom template owns Consent Mode state through `setDefaultConsentState` and `updateConsentState`.
- Application code communicates a change by writing the cookie and pushing `consent_preferences_updated`; it never calls `gtag('consent', ...)`.

## Canonical sequence

1. Initialize `window.dataLayer` without replacing an existing array.
2. On first visit, create the configured default only when no valid stored choice exists.
3. Load GTM only when analytics consent is initially granted.
4. Fire `Consent Mode — Initialize` on Consent Initialization. The template defaults all configured categories and then restores the validated cookie before measurement tags.
5. When the visitor saves preferences, write the versioned cookie and push `consent_preferences_updated` on the same page.
6. Fire `Consent Mode — Update` for that Custom Event and call `updateConsentState` from the template.
7. Keep an already-loaded container mounted long enough to process withdrawal. On a later denied page load, do not load GTM.

The cookie keeps the seven Google consent keys at top level so GTM can read it, plus `version`, `source`, and `updated_at`. Legacy objects with all seven valid states migrate without changing the choice. Malformed/incomplete objects are treated as no valid decision and surfaced to the UI; never silently auto-grant over a malformed stored value.

## Verification matrix

Verify first visit, stored grant, stored denial, granular choice, same-page withdrawal, later reload, and malformed legacy storage. For each scenario capture the earliest consent state, update event, tags fired/not fired, storage, and network requests.

Primary references:

- https://developers.google.com/tag-platform/security/guides/consent
- https://developers.google.com/tag-platform/tag-manager/templates/consent-apis
- https://developers.google.com/tag-platform/security/guides/consent-debugging
