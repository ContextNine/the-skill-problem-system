## Bitwarden

Dependency IDs: `bitwarden` and `bitwarden-cli`.

The desktop application is a required macOS worker application installed by the reviewed onboarding adapter. Verify `/Applications/Bitwarden.app`, its bundle identity, and successful launch before acceptance.

The `bw` CLI is a Homebrew-managed macOS package for explicitly approved repository workflows. Verify it with `bw --version`. Sign-in, MFA, device approval, and vault unlock remain user checkpoints. Automation must not read or copy vault contents or session state. A user-run script may write a supplied file to its own known vault item after the user unlocks the CLI. It must not search the vault, retrieve attachments, manage authentication, print session values, or store session values in files.

Use the vendor updater or approved package channel, preserve data during repair, and treat uninstall or account removal as separately authorized.
