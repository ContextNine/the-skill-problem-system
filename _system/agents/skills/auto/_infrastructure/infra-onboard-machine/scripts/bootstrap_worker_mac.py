#!/usr/bin/env python3
"""Provision and verify a disabled worker Mac in explicit phases."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any
from urllib.request import Request, urlopen


REGISTRY_RELATIVE = Path(
    "_system/agents/_package/instance/fleet/machines.json"
)
WORKER_BOOTSTRAP_RELATIVE = Path("_system/commands/worker_bootstrap.py")
DEPENDENCY_INSTALLER_RELATIVE = Path("_system/deps/install.py")
MAC_STARTUP_RELATIVE = Path("_system/commands/mac_startup.py")
SCRIPT_RELATIVE = Path(
    "_system/agents/skills/auto/_infrastructure/"
    "infra-onboard-machine/scripts/bootstrap_worker_mac.py"
)

T3_RELEASES_URL = "https://api.github.com/repos/pingdotgg/t3code/releases?per_page=20"
T3_BUNDLE_ID = "com.t3tools.t3code"
T3_TEAM_ID = "ARK85ZXQ4Z"
T3_DEFAULT_APP = Path("/Applications/T3 Code (Nightly).app")

APP_SPECS = (
    {
        "name": "Bitwarden",
        "path": Path("/Applications/Bitwarden.app"),
        "bundle_id": "com.bitwarden.desktop",
        "team_id": "LTZ2PFU5D6",
        "cask": "bitwarden",
    },
    {
        "name": "ChatGPT",
        "path": Path("/Applications/ChatGPT.app"),
        "bundle_id": "com.openai.codex",
        "team_id": "2DC432GLL2",
        "cask": "chatgpt",
    },
    {
        "name": "Google Chrome",
        "path": Path("/Applications/Google Chrome.app"),
        "bundle_id": "com.google.Chrome",
        "team_id": "EQHXZ8M8AV",
        "cask": "google-chrome",
    },
)

WIREGUARD_SPEC = {
    "name": "WireGuard",
    "path": Path("/Applications/WireGuard.app"),
    "bundle_id": "com.wireguard.macos",
    "team_id": "L82V4Y2P3C",
}

AMPHETAMINE_APP = Path("/Applications/Amphetamine.app")
AMPHETAMINE_PREFERENCES = (
    Path.home()
    / "Library/Containers/com.if.Amphetamine/Data/Library/Preferences/com.if.Amphetamine.plist"
)
POWER_MANAGEMENT_PLIST = Path("/Library/Preferences/com.apple.PowerManagement.plist")
MACHINE_ID_PATH = Path.home() / ".config/vault/machine-id"


class BootstrapError(RuntimeError):
    """A deterministic bootstrap or verification failure."""


class ManualCheckpoint(BootstrapError):
    """Work must pause for a local, GUI, authentication, or approval action."""

    def __init__(self, heading: str, steps: list[str]):
        super().__init__(heading)
        self.heading = heading
        self.steps = steps


@dataclass(frozen=True)
class T3Release:
    version: str
    tag: str
    asset_name: str
    url: str
    sha256: str


def run(
    argv: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    timeout: int = 1800,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=cwd,
        text=True,
        input=input_text,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
        timeout=timeout,
    )


def find_root(start: Path | None = None) -> Path:
    candidate = (start or Path(__file__)).expanduser().resolve()
    if candidate.is_file():
        candidate = candidate.parent
    for parent in (candidate, *candidate.parents):
        if (parent / "AGENTS.md").is_file() and (parent / "_system/commands").is_dir():
            return parent
    raise BootstrapError("could not locate vault root")


def load_registry(root: Path) -> dict[str, Any]:
    path = root / REGISTRY_RELATIVE
    if not path.is_file():
        raise BootstrapError(f"private machine registry is missing: {path}")
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BootstrapError(f"invalid private machine registry: {exc}") from exc
    version = registry.get("schema_version")
    if not isinstance(version, int) or version < 1:
        raise BootstrapError("private machine registry needs a positive integer schema_version")
    if not isinstance(registry.get("machines"), list):
        raise BootstrapError("private machine registry has no machines array")
    return registry


def resolve_worker_mac(
    registry: dict[str, Any], machine_id: str, *, require_disabled: bool
) -> dict[str, Any]:
    matches = [machine for machine in registry["machines"] if machine.get("id") == machine_id]
    if len(matches) != 1:
        raise BootstrapError(f"unknown exact machine id: {machine_id}")
    machine = matches[0]
    if require_disabled and machine.get("enabled") is not False:
        raise BootstrapError(
            f"worker Mac bootstrap requires a disabled machine: {machine_id}"
        )
    if machine.get("role") != "worker" or machine.get("platform") != "macos":
        raise BootstrapError(f"machine is not a macOS worker: {machine_id}")
    if machine.get("transport") != "ssh" or not machine.get("ssh_alias"):
        raise BootstrapError(f"machine has no reviewed SSH transport: {machine_id}")
    home = str(machine.get("home", ""))
    if not PurePosixPath(home).is_absolute() or any(character.isspace() for character in home):
        raise BootstrapError(f"machine has unsafe or missing home path: {machine_id}")
    vault = machine.get("vault")
    roots = machine.get("roots")
    if not isinstance(vault, dict) or vault.get("enabled") is not True or not isinstance(roots, dict):
        raise BootstrapError(f"vault worker sync is not enabled for provisioning: {machine_id}")
    resolved_vault_root(machine)
    if vault.get("checkout_mode") != "icloud-gitless":
        raise BootstrapError(
            f"worker Mac requires Gitless iCloud vault checkout: {machine_id}"
        )
    return machine


def resolved_vault_root(machine: dict[str, Any]) -> str:
    home = str(machine.get("home") or "")
    roots = machine.get("roots")
    raw = roots.get("vault") if isinstance(roots, dict) else None
    if not isinstance(raw, str) or not raw or "$" in raw:
        raise BootstrapError(f"machine has no safe Vault root: {machine.get('id')}")
    resolved = PurePosixPath(home).joinpath(*PurePosixPath(raw[2:]).parts) if raw.startswith("~/") else PurePosixPath(raw)
    if not resolved.is_absolute() or ".." in resolved.parts:
        raise BootstrapError(f"machine has no safe Vault root: {machine.get('id')}")
    return resolved.as_posix()


def resolve_disabled_worker_mac(
    registry: dict[str, Any], machine_id: str
) -> dict[str, Any]:
    return resolve_worker_mac(registry, machine_id, require_disabled=True)


def git_config(root: Path, key: str) -> str | None:
    result = run(
        ["git", "-C", str(root), "config", "--local", "--get", key],
        check=False,
        timeout=30,
    )
    value = result.stdout.strip()
    return value or None


def machine_identity(root: Path) -> str | None:
    try:
        value = MACHINE_ID_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        value = ""
    return value or git_config(root, "vault.machine-id")


def require_primary(root: Path, registry: dict[str, Any]) -> None:
    expected = registry.get("primary_machine_id")
    actual = git_config(root, "vault.machine-id")
    if not isinstance(expected, str) or not expected:
        raise BootstrapError("registry primary_machine_id is missing")
    if actual != expected:
        raise BootstrapError(
            f"run worker Mac bootstrap from primary clone {expected!r}; current clone is {actual!r}"
        )


def route_alias(machine: dict[str, Any], route: str) -> str:
    base = str(machine["ssh_alias"])
    return base if route == "automatic" else f"{base}-{route}"


def ssh_run(
    machine: dict[str, Any],
    script: str,
    *,
    route: str = "lan",
    check: bool = True,
    timeout: int = 1800,
) -> subprocess.CompletedProcess[str]:
    command = "exec /bin/zsh -lc " + shlex.quote(script)
    return run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            route_alias(machine, route),
            command,
        ],
        check=check,
        timeout=timeout,
    )


def parse_key_values(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        key, separator, value = line.partition("\t")
        if separator:
            result[key] = value
    return result


def remote_facts(machine: dict[str, Any]) -> dict[str, str]:
    script = r'''
set -u
printf 'product\t%s\n' "$(/usr/bin/sw_vers -productName 2>/dev/null || true)"
printf 'version\t%s\n' "$(/usr/bin/sw_vers -productVersion 2>/dev/null || true)"
printf 'arch\t%s\n' "$(/usr/bin/uname -m)"
printf 'home\t%s\n' "$HOME"
printf 'hostname\t%s\n' "$(/bin/hostname)"
if /usr/bin/xcode-select -p >/dev/null 2>&1; then printf 'clt\tyes\n'; else printf 'clt\tno\n'; fi
if [ -x /opt/homebrew/bin/brew ]; then
  printf 'brew\t/opt/homebrew/bin/brew\n'
elif [ -x /usr/local/bin/brew ]; then
  printf 'brew\t/usr/local/bin/brew\n'
else
  printf 'brew\t\n'
fi
'''
    result = ssh_run(machine, script, route="lan")
    facts = parse_key_values(result.stdout)
    if facts.get("product") != "macOS":
        raise BootstrapError(
            f"SSH target is not macOS: {facts.get('product') or 'unknown'}"
        )
    if facts.get("home") != machine["home"]:
        raise BootstrapError(
            f"SSH target home mismatch: expected {machine['home']}, got {facts.get('home')!r}"
        )
    return facts


def remote_auth_facts(machine: dict[str, Any], brew: str) -> dict[str, bool]:
    machine_id = shlex.quote(str(machine["id"]))
    script = f'''
set -u
eval "$({shlex.quote(brew)} shellenv)"
attestation="$HOME/Library/Application Support/Vault Worker Bootstrap/auth-attestation.json"
attested=no
if [ -f "$attestation" ] && [ "$(/usr/bin/plutil -extract machineId raw -o - "$attestation" 2>/dev/null || true)" = {machine_id} ] && [ "$(/usr/bin/plutil -extract githubAuthenticated raw -o - "$attestation" 2>/dev/null || true)" = true ] && [ "$(/usr/bin/plutil -extract codexAuthenticated raw -o - "$attestation" 2>/dev/null || true)" = true ]; then
  attested=yes
fi
if gh auth status --hostname github.com >/dev/null 2>&1 || [ "$attested" = yes ]; then printf 'gh_auth\tyes\n'; else printf 'gh_auth\tno\n'; fi
key="$HOME/.ssh/id_ed25519_github_{machine_id}"
if [ "$(gh config get git_protocol --host github.com 2>/dev/null || true)" = ssh ]; then printf 'gh_protocol_ssh\tyes\n'; else printf 'gh_protocol_ssh\tno\n'; fi
ssh_output="$(ssh -n -o BatchMode=yes -o ConnectTimeout=10 -o ConnectionAttempts=1 -o StrictHostKeyChecking=yes -o IdentitiesOnly=yes -i "$key" -T git@github.com 2>&1 || true)"
case "$ssh_output" in *successfully\ authenticated*) printf 'github_ssh\tyes\n';; *) printf 'github_ssh\tno\n';; esac
if [ -f "$HOME/.config/gh/hosts.yml" ] && /usr/bin/grep -q '^[[:space:]]*oauth_token:' "$HOME/.config/gh/hosts.yml"; then printf 'plaintext_oauth\tyes\n'; else printf 'plaintext_oauth\tno\n'; fi
if command -v codex >/dev/null 2>&1 && codex login status >/dev/null 2>&1 || [ "$attested" = yes ]; then printf 'codex_auth\tyes\n'; else printf 'codex_auth\tno\n'; fi
printf 'gui_attestation\t%s\n' "$attested"
'''
    values = parse_key_values(ssh_run(machine, script, route="lan").stdout)
    return {key: value == "yes" for key, value in values.items()}


def codex_worker_config_status(path: Path | None = None) -> dict[str, bool]:
    """Read only the three worker-policy keys from Codex's TOML config."""
    config = path or (Path.home() / ".codex/config.toml")
    result = {
        "approvalPolicyNever": False,
        "dangerFullAccess": False,
        "computerUseEnabled": False,
    }
    try:
        lines = config.read_text(encoding="utf-8").splitlines()
    except OSError:
        return result
    table = ""
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            table = line[1:-1].strip()
            continue
        key, separator, value = line.partition("=")
        if not separator:
            continue
        key = key.strip()
        value = value.split("#", 1)[0].strip()
        if not table and key == "approval_policy":
            result["approvalPolicyNever"] = value == '"never"'
        elif not table and key == "sandbox_mode":
            result["dangerFullAccess"] = value == '"danger-full-access"'
        elif table == "mcp_servers.computer-use" and key == "enabled":
            result["computerUseEnabled"] = value == "true"
    return result


def seed_script(brew: str, machine_id: str) -> str:
    application_steps: list[str] = []
    for index, spec in enumerate(APP_SPECS):
        variable = f"seed_app_{index}"
        application_steps.append(
            f'''
{variable}={shlex.quote(str(spec['path']))}
if [ ! -d "${variable}" ] && [ -d "$HOME/Applications/{spec['path'].name}" ]; then
  {variable}="$HOME/Applications/{spec['path'].name}"
fi
if [ ! -d "${variable}" ]; then
  {shlex.quote(brew)} install --cask {shlex.quote(str(spec['cask']))}
  {variable}={shlex.quote(str(spec['path']))}
fi
bundle_id=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "${variable}/Contents/Info.plist")
[ "$bundle_id" = {shlex.quote(str(spec['bundle_id']))} ]
team_id=$(/usr/bin/codesign -dv --verbose=4 "${variable}" 2>&1 | /usr/bin/sed -n 's/^TeamIdentifier=//p')
[ "$team_id" = {shlex.quote(str(spec['team_id']))} ]
/usr/bin/codesign --verify --deep --strict "${variable}"
/usr/sbin/spctl --assess --type execute "${variable}"
'''
        )
    auth_helper = f'''#!/bin/zsh
set -euo pipefail
eval "$({shlex.quote(brew)} shellenv)"
gh auth status --hostname github.com >/dev/null
gh api user --jq .login >/dev/null
[ "$(gh config get git_protocol --host github.com)" = ssh ]
if [ -f "$HOME/.config/gh/hosts.yml" ] && /usr/bin/grep -q '^[[:space:]]*oauth_token:' "$HOME/.config/gh/hosts.yml"; then
  print -u2 'refusing attestation: GitHub token is stored in plaintext'
  exit 1
fi
key="$HOME/.ssh/id_ed25519_github_{machine_id}"
test -f "$key" && test -f "$key.pub"
ssh_output="$(ssh -n -o BatchMode=yes -o ConnectTimeout=10 -o ConnectionAttempts=1 -o StrictHostKeyChecking=yes -o IdentitiesOnly=yes -i "$key" -T git@github.com 2>&1 || true)"
case "$ssh_output" in *successfully\ authenticated*) ;; *) print -u2 'refusing attestation: GitHub SSH authentication failed'; exit 1;; esac
codex login status >/dev/null
state_dir="$HOME/Library/Application Support/Vault Worker Bootstrap"
/bin/mkdir -p "$state_dir"
umask 077
verified_at="$(/bin/date -u +%Y-%m-%dT%H:%M:%SZ)"
temporary="$(/usr/bin/mktemp "$state_dir/auth-attestation.XXXXXX")"
/usr/bin/printf '{{"schemaVersion":2,"machineId":%s,"githubAuthenticated":true,"githubProtocolSsh":true,"githubSshAuthenticated":true,"codexAuthenticated":true,"verifiedAt":"%s"}}\\n' {shlex.quote(json.dumps(machine_id))} "$verified_at" > "$temporary"
/bin/chmod 600 "$temporary"
/bin/mv "$temporary" "$state_dir/auth-attestation.json"
print 'Authentication verified in the logged-in GUI session; no account or secret was recorded.'
'''
    return f'''
set -euo pipefail
eval "$({shlex.quote(brew)} shellenv)"
{shlex.quote(brew)} install git git-lfs gh
{''.join(application_steps)}

if ! command -v codex >/dev/null 2>&1; then
  {shlex.quote(brew)} install --cask codex
fi
/bin/mkdir -p "$HOME/.local/bin"
/usr/bin/printf %s {shlex.quote(auth_helper)} > "$HOME/.local/bin/vault-worker-auth-attest"
/bin/chmod 700 "$HOME/.local/bin/vault-worker-auth-attest"
command -v git >/dev/null
command -v git-lfs >/dev/null
command -v gh >/dev/null
command -v codex >/dev/null
'''


def command_status(root: Path, machine_id: str, *, json_output: bool) -> int:
    registry = load_registry(root)
    require_primary(root, registry)
    machine = resolve_disabled_worker_mac(registry, machine_id)
    facts = remote_facts(machine)
    payload = {
        "machineId": machine_id,
        "enabled": machine["enabled"],
        "sshAlias": machine["ssh_alias"],
        "lanAlias": route_alias(machine, "lan"),
        "vaultRepoPath": resolved_vault_root(machine),
        "remote": facts,
    }
    if facts.get("brew"):
        payload["authentication"] = remote_auth_facts(machine, facts["brew"])
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"machine: {machine_id} (disabled macOS worker)")
        print(f"LAN SSH: {route_alias(machine, 'lan')}")
        for key in ("hostname", "version", "arch", "home", "clt", "brew"):
            print(f"{key}: {facts.get(key) or 'missing'}")
        authentication = payload.get("authentication")
        if isinstance(authentication, dict):
            for key, value in authentication.items():
                print(f"{key}: {'yes' if value else 'no'}")
    return 0


def command_seed(root: Path, machine_id: str, *, apply: bool) -> int:
    registry = load_registry(root)
    require_primary(root, registry)
    machine = resolve_disabled_worker_mac(registry, machine_id)
    facts = remote_facts(machine)
    manual: list[str] = []
    if facts.get("clt") != "yes":
        manual.append(
            "Through Screen Sharing, run `xcode-select --install` and complete the Apple installer; hand the license or password prompt to the user only when required."
        )
    brew = facts.get("brew", "")
    if not brew:
        manual.append(
            "Through Screen Sharing, install Homebrew from https://brew.sh; hand the password prompt to the user, then resume from the primary."
        )
    if manual:
        raise ManualCheckpoint("Seed prerequisites are incomplete", manual)

    print(f"machine: {machine_id}")
    print("would install or validate: git, git-lfs, gh, Bitwarden, Google Chrome, ChatGPT desktop, Codex CLI")
    if not apply:
        print("DRY RUN: no target changes made")
        return 0

    ssh_run(machine, seed_script(brew, machine_id), route="lan")
    auth = remote_auth_facts(machine, brew)
    steps: list[str] = []
    if not auth.get("gh_auth"):
        steps.append(
            "Through the initial-onboarding GUI checkpoint, run `gh auth login --hostname github.com --git-protocol ssh --skip-ssh-key --web`; stop before account selection and ask the user to complete authorization and MFA."
        )
    if not auth.get("gh_protocol_ssh"):
        steps.append("Run `gh config set git_protocol ssh --host github.com` in the authenticated worker session.")
    if not auth.get("github_ssh"):
        steps.append(
            "From Primary machine, run the infra-onboard-machine GitHub fleet-auth provision and enrollment workflow for this machine; key enrollment is a separate human approval checkpoint."
        )
    if auth.get("plaintext_oauth"):
        steps.append(
            "Repair GitHub CLI credential storage so hosts.yml has no plaintext oauth_token before continuing."
        )
    if not auth.get("codex_auth"):
        steps.append(
            "Through Screen Sharing, start `codex login --device-auth`, open the device page, then stop and ask the user to complete `Continue with Google` and choose the correct Google account; verify `codex login status`."
        )
    steps.extend(
        [
            "Sign in to and unlock Bitwarden; complete any MFA or device approval yourself.",
            "Ask the user to sign Chrome into the intended Google profile; never infer identity from autofill or saved-account suggestions.",
            "Open ChatGPT, then ask the user to complete `Continue with Google`; never select a saved account on their behalf.",
            "After GitHub and Codex checks succeed in the worker's Screen Sharing Terminal, run `~/.local/bin/vault-worker-auth-attest` to record a secret-free GUI-session attestation.",
            "After each non-delegable prompt, return control to the primary-host agent so it can continue the same workflow.",
        ]
    )
    if not all(
        (
            auth.get("gh_auth"),
            auth.get("gh_protocol_ssh"),
            auth.get("github_ssh"),
            not auth.get("plaintext_oauth"),
            auth.get("codex_auth"),
        )
    ):
        raise ManualCheckpoint("Target-local authentication is required", steps)
    print("seed complete; GitHub OAuth API access and dedicated SSH Git transport verified")
    return 0


def plist_value(app: Path, key: str) -> str:
    info = app / "Contents/Info.plist"
    if not info.is_file():
        raise BootstrapError(f"application Info.plist is missing: {app}")
    try:
        with info.open("rb") as handle:
            value = plistlib.load(handle).get(key)
    except (OSError, plistlib.InvalidFileException) as exc:
        raise BootstrapError(f"cannot read application metadata: {app}: {exc}") from exc
    if not isinstance(value, str) or not value:
        raise BootstrapError(f"application metadata {key} is missing: {app}")
    return value


def app_team_id(app: Path) -> str:
    result = run(
        ["/usr/bin/codesign", "-dv", "--verbose=4", str(app)],
        check=False,
        timeout=60,
    )
    output = result.stdout + result.stderr
    match = re.search(r"^TeamIdentifier=(\S+)$", output, flags=re.MULTILINE)
    if not match:
        raise BootstrapError(f"application TeamIdentifier is missing: {app}")
    return match.group(1)


def validate_application(
    app: Path, *, bundle_id: str, team_id: str, expected_version: str | None = None
) -> str:
    if not app.is_dir():
        raise BootstrapError(f"application is missing: {app}")
    actual_bundle = plist_value(app, "CFBundleIdentifier")
    if actual_bundle != bundle_id:
        raise BootstrapError(
            f"unexpected bundle identifier at {app}: {actual_bundle}"
        )
    version = plist_value(app, "CFBundleShortVersionString")
    if expected_version is not None and version != expected_version:
        raise BootstrapError(
            f"unexpected application version at {app}: {version}; expected {expected_version}"
        )
    actual_team = app_team_id(app)
    if actual_team != team_id:
        raise BootstrapError(f"unexpected signing team at {app}: {actual_team}")
    run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app)], timeout=120)
    run(["/usr/sbin/spctl", "--assess", "--type", "execute", str(app)], timeout=120)
    return version


def brew_path() -> str:
    for candidate in ("/opt/homebrew/bin/brew", "/usr/local/bin/brew"):
        if Path(candidate).is_file():
            return candidate
    raise ManualCheckpoint(
        "Homebrew is required",
        ["Install Homebrew from https://brew.sh on the worker Mac, then rerun finish."],
    )


def ensure_cask_application(spec: dict[str, object], brew: str, *, apply: bool) -> None:
    app = find_application(
        str(spec["bundle_id"]), preferred=Path(spec["path"])
    )
    if app is not None:
        version = validate_application(
            app,
            bundle_id=str(spec["bundle_id"]),
            team_id=str(spec["team_id"]),
        )
        print(f"preserved signed {spec['name']} {version}: {app}")
        return
    print(f"would install {spec['name']} with Homebrew cask {spec['cask']}")
    if not apply:
        return
    run([brew, "install", "--cask", str(spec["cask"])])
    app = find_application(
        str(spec["bundle_id"]), preferred=Path(spec["path"])
    )
    if app is None:
        raise BootstrapError(f"{spec['name']} is missing after Homebrew installation")
    version = validate_application(
        app,
        bundle_id=str(spec["bundle_id"]),
        team_id=str(spec["team_id"]),
    )
    print(f"installed signed {spec['name']} {version}: {app}")


def select_t3_release(payload: object, arch: str) -> T3Release:
    if arch not in {"arm64", "x86_64"}:
        raise BootstrapError(f"unsupported macOS architecture for T3: {arch}")
    if not isinstance(payload, list):
        raise BootstrapError("T3 releases response is not a JSON array")
    suffix = "arm64.dmg" if arch == "arm64" else "x64.dmg"
    for release in payload:
        if not isinstance(release, dict) or release.get("prerelease") is not True:
            continue
        tag = release.get("tag_name")
        if not isinstance(tag, str) or not re.fullmatch(r"v[0-9.]+-nightly\.[0-9.]+", tag):
            continue
        version = tag.removeprefix("v")
        expected_name = f"T3-Code-{version}-{suffix}"
        assets = release.get("assets")
        if not isinstance(assets, list):
            continue
        matches = [asset for asset in assets if isinstance(asset, dict) and asset.get("name") == expected_name]
        if len(matches) != 1:
            continue
        asset = matches[0]
        digest = asset.get("digest")
        url = asset.get("browser_download_url")
        if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise BootstrapError(f"T3 release asset has no valid SHA-256 digest: {expected_name}")
        if not isinstance(url, str) or not url.startswith(
            f"https://github.com/pingdotgg/t3code/releases/download/{tag}/"
        ):
            raise BootstrapError(f"T3 release asset has an unexpected URL: {expected_name}")
        return T3Release(
            version=version,
            tag=tag,
            asset_name=expected_name,
            url=url,
            sha256=digest.removeprefix("sha256:"),
        )
    raise BootstrapError("no qualifying T3 Code nightly DMG found")


def fetch_t3_release(arch: str) -> T3Release:
    request = Request(
        T3_RELEASES_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "worker-mac-bootstrap",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except (OSError, ValueError) as exc:
        raise BootstrapError(f"cannot resolve latest T3 nightly: {exc}") from exc
    return select_t3_release(payload, arch)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_t3_install() -> Path | None:
    if T3_DEFAULT_APP.is_dir():
        return T3_DEFAULT_APP
    candidates: list[Path] = []
    for directory in (Path("/Applications"), Path.home() / "Applications"):
        if not directory.is_dir():
            continue
        for app in directory.glob("*.app"):
            if ".backup" in app.name or ".bootstrap-" in app.name:
                continue
            try:
                if plist_value(app, "CFBundleIdentifier") == T3_BUNDLE_ID:
                    candidates.append(app)
            except BootstrapError:
                continue
    if len(candidates) > 1:
        raise BootstrapError(
            "multiple active T3 Code app bundles found: "
            + ", ".join(str(path) for path in candidates)
        )
    return candidates[0] if candidates else None


def find_application(bundle_id: str, *, preferred: Path) -> Path | None:
    if preferred.is_dir():
        if plist_value(preferred, "CFBundleIdentifier") != bundle_id:
            raise BootstrapError(
                f"unexpected application occupies required path: {preferred}"
            )
        return preferred
    candidates: list[Path] = []
    for directory in (Path("/Applications"), Path.home() / "Applications"):
        if not directory.is_dir():
            continue
        for app in directory.glob("*.app"):
            if ".backup" in app.name or ".bootstrap-" in app.name:
                continue
            try:
                if plist_value(app, "CFBundleIdentifier") == bundle_id:
                    candidates.append(app)
            except BootstrapError:
                continue
    unique = list(dict.fromkeys(candidates))
    if len(unique) > 1:
        raise BootstrapError(
            f"multiple active application bundles found for {bundle_id}: "
            + ", ".join(str(path) for path in unique)
        )
    return unique[0] if unique else None


def install_t3_nightly(*, apply: bool) -> None:
    arch = run(["/usr/bin/uname", "-m"], timeout=30).stdout.strip()
    release = fetch_t3_release(arch)
    existing = find_t3_install()
    if existing is not None:
        version = validate_application(
            existing, bundle_id=T3_BUNDLE_ID, team_id=T3_TEAM_ID
        )
        if version == release.version:
            print(f"T3 Code Nightly already current: {version}")
            return
    destination = existing or T3_DEFAULT_APP
    print(f"would install T3 Code Nightly {release.version} at {destination}")
    if not apply:
        return

    with tempfile.TemporaryDirectory(prefix="worker-mac-t3-") as temporary:
        temp = Path(temporary)
        dmg = temp / release.asset_name
        mount = temp / "mount"
        mount.mkdir()
        run(["/usr/bin/curl", "-fL", "--retry", "3", "-o", str(dmg), release.url])
        actual_digest = sha256(dmg)
        if actual_digest != release.sha256:
            raise BootstrapError(
                f"T3 DMG digest mismatch: expected {release.sha256}, got {actual_digest}"
            )
        run(
            [
                "/usr/bin/hdiutil",
                "attach",
                "-readonly",
                "-nobrowse",
                "-mountpoint",
                str(mount),
                str(dmg),
            ]
        )
        try:
            candidates = list(mount.glob("*.app"))
            if len(candidates) != 1:
                raise BootstrapError("T3 DMG must contain exactly one application bundle")
            candidate = candidates[0]
            validate_application(
                candidate,
                bundle_id=T3_BUNDLE_ID,
                team_id=T3_TEAM_ID,
                expected_version=release.version,
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y%m%dT%H%M%S")
            staging = destination.parent / f".{destination.name}.bootstrap-new-{stamp}"
            backup = destination.parent / f".{destination.name}.bootstrap-backup-{stamp}"
            if staging.exists() or backup.exists():
                raise BootstrapError("T3 staging or backup path already exists")
            run(["/usr/bin/ditto", str(candidate), str(staging)])
            validate_application(
                staging,
                bundle_id=T3_BUNDLE_ID,
                team_id=T3_TEAM_ID,
                expected_version=release.version,
            )
            run(
                [
                    "/usr/bin/osascript",
                    "-e",
                    f'tell application id "{T3_BUNDLE_ID}" to quit',
                ],
                check=False,
                timeout=30,
            )
            time.sleep(2)
            moved_existing = False
            try:
                if destination.exists():
                    os.replace(destination, backup)
                    moved_existing = True
                os.replace(staging, destination)
                validate_application(
                    destination,
                    bundle_id=T3_BUNDLE_ID,
                    team_id=T3_TEAM_ID,
                    expected_version=release.version,
                )
            except Exception:
                if destination.exists():
                    shutil.rmtree(destination)
                if moved_existing and backup.exists():
                    os.replace(backup, destination)
                raise
            finally:
                if staging.exists():
                    shutil.rmtree(staging)
            if backup.exists():
                shutil.rmtree(backup)
        finally:
            run(["/usr/bin/hdiutil", "detach", str(mount)], check=False, timeout=120)
    print(f"installed and verified T3 Code Nightly {release.version}")


def require_target_identity(
    root: Path, *, require_disabled: bool = True
) -> tuple[dict[str, Any], dict[str, Any]]:
    if sys.platform != "darwin":
        raise BootstrapError("target phase requires macOS")
    registry = load_registry(root)
    machine_id = machine_identity(root)
    if not machine_id:
        raise BootstrapError("target has no machine-local Vault identity")
    machine = resolve_worker_mac(
        registry, machine_id, require_disabled=require_disabled
    )
    return registry, machine


def command_target_install(root: Path, *, apply: bool) -> int:
    _, machine = require_target_identity(root)
    brew = brew_path()
    print(f"target machine: {machine['id']}")
    print(f"would run shared dependency installer: {root / DEPENDENCY_INSTALLER_RELATIVE}")
    if apply:
        run(["/bin/bash", str(root / DEPENDENCY_INSTALLER_RELATIVE)], cwd=root)
    for spec in APP_SPECS:
        ensure_cask_application(spec, brew, apply=apply)
    codex = executable_path("codex")
    if codex:
        print(run([codex, "--version"], timeout=60).stdout.strip())
    else:
        print("would install Codex CLI with Homebrew cask codex")
        if apply:
            run([brew, "install", "--cask", "codex"])
            codex = executable_path("codex")
            if not codex:
                raise BootstrapError("Codex CLI is missing after Homebrew installation")
            print(run([codex, "--version"], timeout=60).stdout.strip())
    install_t3_nightly(apply=apply)
    if not apply:
        print("DRY RUN: no target changes made")
        return 0

    startup = run(
        [
            sys.executable,
            str(root / MAC_STARTUP_RELATIVE),
            "--root",
            str(root),
            "install",
            "--provision-disabled",
        ],
        check=False,
    )
    if startup.returncode != 0:
        detail = startup.stderr.strip() or startup.stdout.strip() or "unknown mac-startup error"
        raise ManualCheckpoint(
            "Managed Bitwarden login startup is not configured",
            [
                f"mac-startup reported: {detail}",
                "Add this machine to Mac Startup private config with `open-applications: true` and `applications: [\"com.bitwarden.desktop\"]`.",
                "Rerun the finish phase from the primary Mac.",
            ],
        )
    print(startup.stdout.strip())
    return 0


def command_finish(root: Path, machine_id: str, *, apply: bool) -> int:
    registry = load_registry(root)
    require_primary(root, registry)
    machine = resolve_disabled_worker_mac(registry, machine_id)
    facts = remote_facts(machine)
    brew = facts.get("brew", "")
    if not brew:
        raise ManualCheckpoint(
            "Homebrew is required",
            ["Complete the seed phase on the worker Mac before running finish."],
        )
    auth = remote_auth_facts(machine, brew)
    if not all(
        (
            auth.get("gh_auth"),
            auth.get("gh_protocol_ssh"),
            auth.get("github_ssh"),
            not auth.get("plaintext_oauth"),
            auth.get("codex_auth"),
        )
    ):
        raise ManualCheckpoint(
            "GitHub OAuth or dedicated SSH checkpoint is incomplete",
            [
                "In the worker's Screen Sharing session, ask the user to choose the intended account for each login; never use an autofilled or saved identity as proof.",
                "Run `gh auth login --hostname github.com --git-protocol ssh --skip-ssh-key --web` on the worker Mac and have the user complete account selection and authorization.",
                "Run `gh config set git_protocol ssh --host github.com`.",
                "From Primary machine, provision and explicitly approve enrollment of the worker's dedicated GitHub SSH key.",
                "Run `codex login --device-auth`; ask the user to complete `Continue with Google`, then verify `codex login status`.",
                "Run `~/.local/bin/vault-worker-auth-attest` from the logged-in GUI Terminal, then rerun finish.",
            ],
        )
    repo_path = resolved_vault_root(machine)
    bootstrap = [
        sys.executable,
        str(root / WORKER_BOOTSTRAP_RELATIVE),
        "--root",
        str(root),
        "bootstrap",
        machine_id,
        "--provision-disabled",
    ]
    if apply:
        bootstrap.append("--apply")
    result = run(bootstrap, check=False)
    if result.stdout:
        print(result.stdout.rstrip())
    if result.returncode != 0:
        raise BootstrapError(result.stderr.strip() or "vault worker bootstrap failed")
    target_command = (
        f"python3 {shlex.quote(str(PurePosixPath(repo_path) / SCRIPT_RELATIVE))} "
        f"--root {shlex.quote(repo_path)} target-install"
    )
    if not apply:
        print(f"DRY RUN: would run on {machine['ssh_alias']}: {target_command} --apply")
        return 0
    target = ssh_run(
        machine,
        target_command + " --apply",
        route="automatic",
        check=False,
    )
    if target.stdout:
        print(target.stdout.rstrip())
    if target.returncode == 3:
        raise ManualCheckpoint(
            "Target installation paused for a manual checkpoint",
            [target.stderr.strip() or "Review the target bootstrap output, complete the action, and rerun finish."],
        )
    if target.returncode != 0:
        raise BootstrapError(target.stderr.strip() or "target installation failed")
    print("finish complete; keep the machine disabled until reboot verification passes")
    return 0


def command_exists(name: str) -> tuple[bool, str | None]:
    path = executable_path(name)
    if not path:
        return False, None
    command_path = os.pathsep.join(
        (str(Path(path).parent), os.environ.get("PATH", "/usr/bin:/bin"))
    )
    result = run(
        ["/usr/bin/env", f"PATH={command_path}", path, "--version"],
        check=False,
        timeout=60,
    )
    version = (result.stdout or result.stderr).strip().splitlines()
    return result.returncode == 0, version[0] if version else None


def executable_path(name: str) -> str | None:
    path = shutil.which(name)
    if path:
        return path
    for directory in (Path("/opt/homebrew/bin"), Path("/usr/local/bin"), Path.home() / ".local/bin"):
        candidate = directory / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def application_status(spec: dict[str, object]) -> dict[str, object]:
    preferred = Path(spec["path"])
    try:
        app = find_application(str(spec["bundle_id"]), preferred=preferred)
        if app is None:
            raise BootstrapError(f"application is missing: {preferred}")
        version = validate_application(
            app,
            bundle_id=str(spec["bundle_id"]),
            team_id=str(spec["team_id"]),
        )
        return {"ok": True, "version": version, "path": str(app)}
    except BootstrapError as exc:
        return {"ok": False, "error": str(exc), "path": str(preferred)}


def pmset_ac_settings(text: str) -> dict[str, str]:
    settings: dict[str, str] = {}
    in_ac_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.endswith("Power:"):
            in_ac_section = stripped == "AC Power:"
            continue
        if not in_ac_section or not stripped:
            continue
        key, separator, value = stripped.rpartition(" ")
        if separator and key and value:
            settings[key.strip()] = value.strip()
    return settings


def wireguard_status_flags(text: str) -> dict[str, bool]:
    """Extract unattended-operation gates from `scutil --nc status` output."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return {
        "connected": bool(lines and lines[0] == "Connected")
        and "Status : 2" in text,
        "onDemand": "is-on-demand : TRUE" in text
        and "OnDemandAction : 1" in text,
    }


def screen_lock_is_disabled(text: str) -> bool:
    """Require the explicit disabled state, not an immediate password delay."""
    return "screenLock is off" in text


def amphetamine_preference_flags(path: Path | None = None) -> dict[str, bool]:
    """Read the unattended closed-display session policy from Amphetamine."""
    preferences = path or AMPHETAMINE_PREFERENCES
    try:
        with preferences.open("rb") as handle:
            payload = plistlib.load(handle)
    except (OSError, plistlib.InvalidFileException):
        return {
            "startSessionAtLaunch": False,
            "indefiniteSessionConfigured": False,
            "closedDisplaySleepDisabled": False,
        }
    if not isinstance(payload, dict):
        return {
            "startSessionAtLaunch": False,
            "indefiniteSessionConfigured": False,
            "closedDisplaySleepDisabled": False,
        }
    return {
        "startSessionAtLaunch": payload.get("Start Session At Launch") is True,
        "indefiniteSessionConfigured": payload.get("Default Duration") == 0,
        "closedDisplaySleepDisabled": (
            payload.get("Allow Closed-Display Sleep") is False
        ),
    }


def amphetamine_assertion_active(text: str) -> bool:
    """Require Amphetamine's active single-use system sleep assertion."""
    return "Amphetamine (Single-Use - System)" in text


def automatic_restart_enabled(path: Path | None = None) -> bool:
    """Read the laptop-compatible power-loss setting from its source plist."""
    preferences = path or POWER_MANAGEMENT_PLIST
    try:
        with preferences.open("rb") as handle:
            payload = plistlib.load(handle)
    except (OSError, plistlib.InvalidFileException):
        return False
    if not isinstance(payload, dict):
        return False
    return all(
        isinstance(payload.get(source), dict)
        and payload[source].get("Automatic Restart On Power Loss") == 1
        for source in ("AC Power", "Battery Power")
    )


def default_browser_handlers(path: Path | None = None) -> dict[str, str]:
    preferences = path or (
        Path.home()
        / "Library/Preferences/com.apple.LaunchServices/com.apple.launchservices.secure.plist"
    )
    try:
        with preferences.open("rb") as handle:
            payload = plistlib.load(handle)
    except (OSError, plistlib.InvalidFileException):
        return {}
    entries = payload.get("LSHandlers", []) if isinstance(payload, dict) else []
    handlers: dict[str, str] = {}
    if not isinstance(entries, list):
        return handlers
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        scheme = entry.get("LSHandlerURLScheme")
        role = entry.get("LSHandlerRoleAll")
        if isinstance(scheme, str) and isinstance(role, str):
            handlers[scheme.lower()] = role.lower()
    return handlers


def local_auth_attestation(machine_id: str, path: Path | None = None) -> dict[str, bool]:
    attestation = path or (
        Path.home()
        / "Library/Application Support/Vault Worker Bootstrap/auth-attestation.json"
    )
    try:
        if attestation.stat().st_mode & 0o077:
            return {"githubAuthenticated": False, "codexAuthenticated": False}
        payload = json.loads(attestation.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"githubAuthenticated": False, "codexAuthenticated": False}
    if not isinstance(payload, dict) or payload.get("machineId") != machine_id:
        return {"githubAuthenticated": False, "codexAuthenticated": False}
    return {
        "githubAuthenticated": payload.get("githubAuthenticated") is True
        and payload.get("githubProtocolSsh") is True
        and payload.get("githubSshAuthenticated") is True,
        "codexAuthenticated": payload.get("codexAuthenticated") is True,
    }


def target_verification(root: Path) -> dict[str, object]:
    # Acceptance remains valid after the registry record is enabled. Mutating
    # target-install phases retain the disabled-machine guard.
    _, machine = require_target_identity(root, require_disabled=False)
    commands = {
        name: {"ok": ok, "version": version}
        for name in ("brew", "git", "git-lfs", "gh", "node", "npm", "codex")
        for ok, version in (command_exists(name),)
    }
    applications = {
        str(spec["name"]): application_status(spec)
        for spec in (*APP_SPECS, WIREGUARD_SPEC)
    }
    t3 = find_t3_install()
    if t3 is None:
        applications["T3 Code Nightly"] = {"ok": False, "error": "application is missing"}
    else:
        applications["T3 Code Nightly"] = application_status(
            {
                "path": t3,
                "bundle_id": T3_BUNDLE_ID,
                "team_id": T3_TEAM_ID,
            }
        )
    gh = executable_path("gh")
    codex = executable_path("codex")
    attested_auth = local_auth_attestation(str(machine["id"]))
    codex_configuration = codex_worker_config_status()
    gh_auth = bool(
        gh
        and run(
            [gh, "auth", "status", "--hostname", "github.com"], check=False
        ).returncode
        == 0
    ) or attested_auth["githubAuthenticated"]
    codex_auth = bool(
        codex and run([codex, "login", "status"], check=False).returncode == 0
    ) or attested_auth["codexAuthenticated"]
    filevault = run(["/usr/bin/fdesetup", "status"], check=False, timeout=60)
    auto_login = run(
        [
            "/usr/bin/defaults",
            "read",
            "/Library/Preferences/com.apple.loginwindow",
            "autoLoginUser",
        ],
        check=False,
        timeout=30,
    )
    auto_logout = run(
        [
            "/usr/bin/defaults",
            "read",
            "/Library/Preferences/com.apple.loginwindow",
            "com.apple.autologout.AutoLogOutDelay",
        ],
        check=False,
        timeout=30,
    )
    screen_lock = run(
        ["/usr/sbin/sysadminctl", "-screenLock", "status"],
        check=False,
        timeout=30,
    )
    screen_sharing = run(
        ["/bin/launchctl", "print", "system/com.apple.screensharing"],
        check=False,
        timeout=30,
    )
    wireguard_status = run(
        ["/usr/sbin/scutil", "--nc", "status", str(machine["id"])],
        check=False,
        timeout=30,
    )
    wireguard_flags = wireguard_status_flags(
        wireguard_status.stdout + wireguard_status.stderr
    )
    wireguard_login_helper = run(
        [
            "/bin/launchctl",
            "print",
            f"gui/{os.getuid()}/com.wireguard.macos.login-item-helper",
        ],
        check=False,
        timeout=30,
    )
    startup = run(
        [
            sys.executable,
            str(root / MAC_STARTUP_RELATIVE),
            "--root",
            str(root),
            "status",
            "--json",
        ],
        check=False,
    )
    startup_payload: dict[str, object] = {}
    if startup.returncode == 0:
        try:
            startup_payload = json.loads(startup.stdout)
        except json.JSONDecodeError:
            startup_payload = {"error": "invalid mac-startup status JSON"}
    sync = machine.get("vault", {})
    git_probe = run(
        ["git", "-C", str(root), "rev-parse", "--git-dir"],
        check=False,
        timeout=30,
    )
    pointer_target: Path | None = None
    pointer_error: str | None = None
    try:
        pointer_text = (root / ".git").read_text(encoding="utf-8").strip()
        prefix = "gitdir: "
        if not pointer_text.startswith(prefix):
            pointer_error = "shared .git file is not a gitdir pointer"
        else:
            candidate = Path(pointer_text[len(prefix) :])
            if not candidate.is_absolute():
                pointer_error = "shared .git pointer target is not absolute"
            else:
                pointer_target = candidate
    except OSError as exc:
        pointer_error = str(exc)
    dataless = run(
        [
            "/usr/bin/find",
            str(root),
            "-flags",
            "+dataless",
            "-print",
            "-quit",
        ],
        check=False,
        timeout=120,
    )
    refresh_schedule = run(
        [
            sys.executable,
            str(root / "_system/commands/refresh_schedule.py"),
            "--root",
            str(root),
            "status",
            "--json",
        ],
        check=False,
        timeout=30,
    )
    refresh_schedule_payload: dict[str, object] = {}
    if refresh_schedule.returncode == 0:
        try:
            refresh_schedule_payload = json.loads(refresh_schedule.stdout)
        except json.JSONDecodeError:
            refresh_schedule_payload = {"error": "invalid refresh-schedule status JSON"}
    power = run(["/usr/bin/pmset", "-g", "custom"], check=False, timeout=30)
    ac_power = pmset_ac_settings(power.stdout)
    battery_match = re.search(
        r"Battery Power:\n(?P<section>.*?)(?=\nAC Power:|\Z)",
        power.stdout,
        flags=re.DOTALL,
    )
    battery_power = pmset_ac_settings(
        "AC Power:\n" + (battery_match.group("section") if battery_match else "")
    )
    browser_handlers = default_browser_handlers()
    wireguard_running = run(
        ["/usr/bin/pgrep", "-f", "WireGuard"], check=False, timeout=30
    ).returncode == 0
    bitwarden_running = run(
        ["/usr/bin/pgrep", "-x", "Bitwarden"], check=False, timeout=30
    ).returncode == 0
    amphetamine_running = run(
        ["/usr/bin/pgrep", "-x", "Amphetamine"], check=False, timeout=30
    ).returncode == 0
    amphetamine_assertions = run(
        ["/usr/bin/pmset", "-g", "assertions"], check=False, timeout=30
    )
    amphetamine_preferences = amphetamine_preference_flags()
    expected_user = Path(str(machine["home"])).name
    automatic_login_user = (
        auto_login.stdout.strip() if auto_login.returncode == 0 else None
    )
    return {
        "machineId": machine["id"],
        "commands": commands,
        "applications": applications,
        "githubAuthenticated": gh_auth,
        "codexAuthenticated": codex_auth,
        "codexConfiguration": codex_configuration,
        "codexComputerUseEnabled": codex_configuration["computerUseEnabled"],
        "codexBypassAllPermissions": codex_configuration["approvalPolicyNever"]
        and codex_configuration["dangerFullAccess"],
        "guiAuthAttestation": attested_auth,
        "fileVaultOff": "FileVault is Off" in (filevault.stdout + filevault.stderr),
        "automaticLoginUser": automatic_login_user,
        "automaticLoginCorrect": automatic_login_user == expected_user,
        "automaticLogoutDisabled": auto_logout.returncode != 0
        or auto_logout.stdout.strip() in ("", "0"),
        "screenLockStatus": (screen_lock.stdout + screen_lock.stderr).strip(),
        "screenLockDisabled": screen_lock_is_disabled(
            screen_lock.stdout + screen_lock.stderr
        ),
        "screenSharingLoaded": screen_sharing.returncode == 0,
        "wireGuardRunning": wireguard_running,
        "wireGuardStatus": (wireguard_status.stdout + wireguard_status.stderr).strip(),
        "wireGuardConnected": wireguard_flags["connected"],
        "wireGuardOnDemand": wireguard_flags["onDemand"],
        "wireGuardLoginHelperEnabled": wireguard_login_helper.returncode == 0,
        "amphetamine": {
            "installed": AMPHETAMINE_APP.is_dir(),
            "running": amphetamine_running,
            **amphetamine_preferences,
            "sessionActive": amphetamine_assertion_active(
                amphetamine_assertions.stdout + amphetamine_assertions.stderr
            ),
        },
        "bitwardenRunning": bitwarden_running,
        "vaultCheckout": sync.get("checkout"),
        "vaultGitPointerTarget": str(pointer_target) if pointer_target else None,
        "vaultGitPointerError": pointer_error,
        "vaultGitPointerDangling": pointer_target is not None
        and not pointer_target.exists(),
        "vaultResolvesAsGitWorktree": git_probe.returncode == 0,
        "vaultMachineIdentity": machine_identity(root),
        "legacyCodeVaultPresent": (Path.home() / "Code/vault").exists(),
        "gitlessICloudCorrect": sync.get("checkout") == "icloud"
        and pointer_error is None
        and pointer_target is not None
        and not pointer_target.exists()
        and git_probe.returncode != 0
        and machine_identity(root) == machine["id"]
        and not (Path.home() / "Code/vault").exists(),
        "iCloudFullyDownloaded": dataless.returncode == 0
        and not dataless.stdout.strip(),
        "datalessExample": dataless.stdout.strip() or None,
        "refreshSchedule": refresh_schedule_payload,
        "refreshScheduleDisabled": refresh_schedule.returncode == 0
        and refresh_schedule_payload.get("loaded") is False
        and refresh_schedule_payload.get("eligible") is False,
        "refreshScheduleBlockedPersistently": "persistent machine-local worker block"
        in str(refresh_schedule_payload.get("blockedReason", "")),
        "macStartup": startup_payload,
        "powerSettings": power.stdout.strip(),
        "dockedPowerOk": ac_power.get("sleep") == "0"
        and ac_power.get("womp") == "1",
        "batteryPowerOk": battery_power.get("sleep") == "0"
        and battery_power.get("womp") == "1",
        "automaticRestartEnabled": automatic_restart_enabled(),
        "defaultBrowserHandlers": browser_handlers,
        "chromeDefaultBrowser": all(
            browser_handlers.get(scheme) == "com.google.chrome"
            for scheme in ("http", "https")
        ),
    }


def target_verification_ok(payload: dict[str, object]) -> bool:
    commands = payload.get("commands", {})
    applications = payload.get("applications", {})
    amphetamine = payload.get("amphetamine", {})
    startup = payload.get("macStartup", {})
    return bool(
        isinstance(commands, dict)
        and commands
        and all(isinstance(value, dict) and value.get("ok") for value in commands.values())
        and isinstance(applications, dict)
        and applications
        and all(isinstance(value, dict) and value.get("ok") for value in applications.values())
        and payload.get("githubAuthenticated")
        and payload.get("codexAuthenticated")
        and payload.get("codexComputerUseEnabled")
        and payload.get("codexBypassAllPermissions")
        and payload.get("fileVaultOff")
        and payload.get("automaticLoginUser")
        and payload.get("automaticLoginCorrect")
        and payload.get("automaticLogoutDisabled")
        and payload.get("screenLockDisabled")
        and payload.get("screenSharingLoaded")
        and payload.get("wireGuardRunning")
        and payload.get("wireGuardConnected")
        and payload.get("wireGuardOnDemand")
        and payload.get("wireGuardLoginHelperEnabled")
        and isinstance(amphetamine, dict)
        and amphetamine.get("installed")
        and amphetamine.get("running")
        and amphetamine.get("startSessionAtLaunch")
        and amphetamine.get("indefiniteSessionConfigured")
        and amphetamine.get("closedDisplaySleepDisabled")
        and amphetamine.get("sessionActive")
        and payload.get("bitwardenRunning")
        and payload.get("gitlessICloudCorrect")
        and payload.get("iCloudFullyDownloaded")
        and payload.get("refreshScheduleDisabled")
        and payload.get("refreshScheduleBlockedPersistently")
        and payload.get("dockedPowerOk")
        and payload.get("batteryPowerOk")
        and payload.get("automaticRestartEnabled")
        and payload.get("chromeDefaultBrowser")
        and isinstance(startup, dict)
        and startup.get("loaded")
        and startup.get("applications") == ["com.bitwarden.desktop"]
    )


def command_target_verify(root: Path, *, json_output: bool) -> int:
    payload = target_verification(root)
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if target_verification_ok(payload) else 1


def probe_alias(alias: str) -> bool:
    result = run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", alias, "true"],
        check=False,
        timeout=10,
    )
    return result.returncode == 0


def command_verify(root: Path, machine_id: str, *, json_output: bool) -> int:
    registry = load_registry(root)
    require_primary(root, registry)
    machine = resolve_disabled_worker_mac(registry, machine_id)
    routes = {
        route: probe_alias(route_alias(machine, route))
        for route in ("lan", "wg", "automatic")
    }
    repo_path = resolved_vault_root(machine)
    command = (
        f"python3 {shlex.quote(str(PurePosixPath(repo_path) / SCRIPT_RELATIVE))} "
        f"--root {shlex.quote(repo_path)} target-verify --json"
    )
    result = ssh_run(machine, command, route="automatic", check=False)
    target: dict[str, object]
    try:
        target = json.loads(result.stdout) if result.stdout else {"error": result.stderr.strip()}
    except json.JSONDecodeError:
        target = {"error": "target verification returned invalid JSON"}
    payload = {"machineId": machine_id, "routes": routes, "target": target}
    print(json.dumps(payload, indent=2, sort_keys=True))
    ok = all(routes.values()) and result.returncode == 0 and target_verification_ok(target)
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="vault root; defaults to auto-discovery")
    subparsers = parser.add_subparsers(dest="command", required=True)
    status = subparsers.add_parser(
        "status", help="inspect the disabled target over its LAN SSH route"
    )
    status.add_argument("machine_id")
    status.add_argument("--json", action="store_true")
    seed = subparsers.add_parser(
        "seed", help="install the pre-clone tools and authentication applications"
    )
    seed.add_argument("machine_id")
    seed.add_argument("--apply", action="store_true")
    finish = subparsers.add_parser(
        "finish", help="prepare the Gitless iCloud vault and run target-local installation"
    )
    finish.add_argument("machine_id")
    finish.add_argument("--apply", action="store_true")
    verify = subparsers.add_parser(
        "verify", help="run final route, application, authentication, and startup checks"
    )
    verify.add_argument("machine_id")
    verify.add_argument("--json", action="store_true")
    target_install = subparsers.add_parser(
        "target-install", help="internal target-local installation phase"
    )
    target_install.add_argument("--apply", action="store_true")
    target_verify = subparsers.add_parser(
        "target-verify", help="internal target-local verification phase"
    )
    target_verify.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = find_root(args.root) if args.root else find_root()
    try:
        if args.command == "status":
            return command_status(root, args.machine_id, json_output=args.json)
        if args.command == "seed":
            return command_seed(root, args.machine_id, apply=args.apply)
        if args.command == "finish":
            return command_finish(root, args.machine_id, apply=args.apply)
        if args.command == "verify":
            return command_verify(root, args.machine_id, json_output=args.json)
        if args.command == "target-install":
            return command_target_install(root, apply=args.apply)
        if args.command == "target-verify":
            return command_target_verify(root, json_output=args.json)
    except ManualCheckpoint as exc:
        print(f"MANUAL CHECKPOINT: {exc.heading}", file=sys.stderr)
        for index, step in enumerate(exc.steps, start=1):
            print(f"{index}. {step}", file=sys.stderr)
        return 3
    except (BootstrapError, OSError, subprocess.SubprocessError) as exc:
        detail = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) and exc.stderr else str(exc)
        print(f"worker-mac bootstrap failed: {detail}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
