# PostHog Error Boundary

Use GA4 for public acquisition and successful marketing outcomes. Use PostHog for signed-in product behavior, replay, feature flags, and client diagnostics. Do not load both automatically on the same host unless a documented reporting requirement justifies it.

## Client exception path

1. Capture browser errors and unhandled rejections.
2. Capture route and global React error-boundary failures explicitly; caught render errors may not reach `window.onerror`.
3. Send the same sanitized error to PostHog `$exception` and a rate-limited server action/logger.
4. Strip URL query strings/fragments, emails, bearer tokens, and obvious secret/token query values.
5. Bound message, stack, source, URL, and user-agent lengths in both client and server schemas.
6. Never attach form values, cookies, authorization headers, raw request bodies, or user-provided documents.

Test the shared reporter locally with mocked PostHog/server calls. Smoke-test initialization in production without deliberately crashing production.
