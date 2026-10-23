## ChatGPT desktop

Dependency ID: `chatgpt-desktop`. It is a required macOS application installed and updated through the Homebrew `chatgpt` cask, then verified at `/Applications/ChatGPT.app` with its signed bundle identity.

Account selection, Google login, MFA, and macOS security prompts are user checkpoints. Application updates and app-only reinstalls must preserve `~/.codex` and Codex data under `~/Library/Application Support`. Never use Homebrew's `--zap` option for an update or repair. Never copy opaque session stores between machines. State deletion requires separate approval.
