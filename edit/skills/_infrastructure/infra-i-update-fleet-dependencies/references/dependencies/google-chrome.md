## Google Chrome

Dependency ID: `google-chrome`. It is a required macOS worker application installed through the onboarding adapter and verified at `/Applications/Google Chrome.app` with bundle ID `com.google.Chrome`.

Profile selection, Google sign-in, sync consent, passkeys, and extension approval are user actions. Updates use the signed vendor channel. Never infer the intended account from saved-account UI. Preserve profiles during repair; removal or profile deletion is separate.
