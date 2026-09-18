#!/usr/bin/env python3
"""Audit and provision per-machine GitHub SSH authentication for the fleet."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
from typing import Any


REGISTRY_RELATIVE = Path(
    "_system/agents/edit/settings/fleet/machines.json"
)
GITHUB_ED25519_HOST_KEY = (
    "github.com ssh-ed25519 "
    "AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl"
)
GITHUB_ED25519_FINGERPRINT = "SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU"


class FleetAuthError(RuntimeError):
    """A deterministic fleet-authentication failure."""


def run(
    command: list[str],
    *,
    input_text: str | None = None,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def output(process: subprocess.CompletedProcess[str]) -> str:
    return process.stdout.strip()


def vault_root() -> Path:
    resolved = run(["vault", "root"])
    if resolved.returncode == 0 and output(resolved):
        return Path(output(resolved)).resolve()
    raise FleetAuthError("cannot resolve the Vault root")


def load_registry(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FleetAuthError(f"cannot read machine registry: {path}: {exc}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("machines"), list):
        raise FleetAuthError(f"invalid machine registry: {path}")
    return value


def current_machine_id(root: Path) -> str:
    result = run(["git", "-C", str(root), "config", "--local", "vault.machine-id"])
    if result.returncode == 0 and output(result):
        return output(result)
    marker = Path.home() / ".config/vault/machine-id"
    try:
        machine_id = marker.read_text(encoding="utf-8").strip()
    except OSError:
        machine_id = ""
    if not machine_id:
        raise FleetAuthError("the executing machine has no Vault machine identity")
    return machine_id


def resolve_machines(
    registry: dict[str, Any], requested: list[str], source_id: str
) -> list[dict[str, Any]]:
    machines = [item for item in registry["machines"] if isinstance(item, dict)]
    if requested:
        selected: list[dict[str, Any]] = []
        for name in requested:
            matches = [
                machine
                for machine in machines
                if name.casefold()
                in {
                    str(machine.get("id", "")).casefold(),
                    str(machine.get("display_name", "")).casefold(),
                }
            ]
            if len(matches) != 1:
                raise FleetAuthError(f"target {name!r} did not resolve exactly once")
            if matches[0] not in selected:
                selected.append(matches[0])
        return selected
    return [machine for machine in machines if machine.get("enabled") or machine.get("id") == source_id]


def public_key_fingerprint(public_key: str) -> str:
    parts = public_key.strip().split()
    if len(parts) < 2 or parts[0] != "ssh-ed25519":
        raise FleetAuthError("expected an Ed25519 public key")
    try:
        raw = base64.b64decode(parts[1], validate=True)
    except ValueError as exc:
        raise FleetAuthError("public key is not valid base64") from exc
    digest = base64.b64encode(hashlib.sha256(raw).digest()).decode().rstrip("=")
    return f"SHA256:{digest}"


def github_keys() -> list[dict[str, object]]:
    result = run(["gh", "api", "user/keys", "--paginate"])
    if result.returncode != 0:
        raise FleetAuthError("Primary machine's authenticated gh session cannot list GitHub SSH keys")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise FleetAuthError("GitHub SSH key inventory returned invalid JSON") from exc
    keys: list[dict[str, object]] = []
    for item in payload if isinstance(payload, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("key"), str):
            continue
        try:
            fingerprint = public_key_fingerprint(str(item["key"]))
        except FleetAuthError:
            continue
        keys.append(
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "fingerprint": fingerprint,
            }
        )
    return keys


def target_command(machine: dict[str, Any], script: str) -> list[str]:
    if machine.get("transport") == "local":
        return ["/bin/sh", "-c", script]
    alias = machine.get("ssh_alias")
    if not isinstance(alias, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", alias):
        raise FleetAuthError(f"machine {machine.get('id')} has no safe SSH alias")
    return [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        alias,
        "/bin/sh -s",
    ]


def target_run(machine: dict[str, Any], script: str) -> subprocess.CompletedProcess[str]:
    if machine.get("transport") == "local":
        return run(target_command(machine, script))
    return run(target_command(machine, script), input_text=script)


def audit_script(machine_id: str) -> str:
    key_name = f"id_ed25519_github_{machine_id}"
    return f'''set -u
key="$HOME/.ssh/{key_name}"
platform="$(uname -s)"
printf 'machine_id\\t%s\\n' {shlex.quote(machine_id)}
printf 'platform\\t%s\\n' "$platform"
if [ "$platform" = Darwin ]; then
  PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
  export PATH
elif [ "$platform" = Linux ]; then
  XDG_RUNTIME_DIR="${{XDG_RUNTIME_DIR:-/run/user/$(id -u)}}"
  DBUS_SESSION_BUS_ADDRESS="${{DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}}"
  export XDG_RUNTIME_DIR DBUS_SESSION_BUS_ADDRESS
fi
if [ -f "$key" ] && [ -f "$key.pub" ]; then
  printf 'private_key\\tyes\\n'
  printf 'public_key\\tyes\\n'
  printf 'fingerprint\\t%s\\n' "$(ssh-keygen -lf "$key.pub" -E sha256 2>/dev/null | awk '{{print $2}}')"
else
  printf 'private_key\\tno\\n'
  printf 'public_key\\tno\\n'
  printf 'fingerprint\\t\\n'
fi
if [ -f "$HOME/.ssh/config.d/ctx9-github.conf" ]; then printf 'managed_config\\tyes\\n'; else printf 'managed_config\\tno\\n'; fi
if [ -f "$HOME/.ssh/config.d/ctx9-github.conf" ] && grep -Fqx '# ctx9-passphrase-free-linux-exception' "$HOME/.ssh/config.d/ctx9-github.conf"; then printf 'passphrase_free_exception\\tyes\\n'; else printf 'passphrase_free_exception\\tno\\n'; fi
if [ -f "$key" ] && ssh-keygen -y -P '' -f "$key" >/dev/null 2>&1; then printf 'passphrase_free_key\\tyes\\n'; else printf 'passphrase_free_key\\tno\\n'; fi
effective_identity="$(ssh -G github.com 2>/dev/null | awk '$1 == "identityfile" {{print $2}}' | head -n 1)"
case "$effective_identity" in *"/{key_name}") printf 'effective_identity\\tyes\\n';; *) printf 'effective_identity\\tno\\n';; esac
if [ -f "$HOME/.ssh/known_hosts" ] && grep -Fqx {shlex.quote(GITHUB_ED25519_HOST_KEY)} "$HOME/.ssh/known_hosts"; then printf 'github_host_key\\tyes\\n'; else printf 'github_host_key\\tno\\n'; fi
native_agent="${{SSH_AUTH_SOCK:-}}"
if [ ! -S "$native_agent" ]; then
  if [ "$platform" = Darwin ]; then
    native_agent="$(launchctl print "gui/$(id -u)/com.openssh.ssh-agent" 2>/dev/null | awk '$1 == "path" && $2 == "=" && $3 ~ /\\/Listeners$/ {{print $3; exit}}')"
  fi
  for candidate in "/run/user/$(id -u)/keyring/ssh" "/run/user/$(id -u)/gnupg/S.gpg-agent.ssh"; do
    if [ -S "$candidate" ]; then native_agent="$candidate"; break; fi
  done
fi
if [ -S "$native_agent" ]; then
  export SSH_AUTH_SOCK="$native_agent"
  printf 'native_agent\\tyes\\n'
else
  printf 'native_agent\\tno\\n'
fi
key_fingerprint="$(ssh-keygen -lf "$key.pub" -E sha256 2>/dev/null | awk '{{print $2}}')"
if [ -n "$key_fingerprint" ] && SSH_AUTH_SOCK="$native_agent" ssh-add -l -E sha256 2>/dev/null | grep -Fq "$key_fingerprint"; then printf 'agent_visible\\tyes\\n'; else printf 'agent_visible\\tno\\n'; fi
gui_gh_attestation=no
attestation="$HOME/Library/Application Support/Vault Worker Bootstrap/auth-attestation.json"
if [ "$platform" = Darwin ] && [ -f "$attestation" ] \
  && [ "$(/usr/bin/plutil -extract machineId raw -o - "$attestation" 2>/dev/null || true)" = {shlex.quote(machine_id)} ] \
  && [ "$(/usr/bin/plutil -extract githubAuthenticated raw -o - "$attestation" 2>/dev/null || true)" = true ]; then
  gui_gh_attestation=yes
fi
printf 'gui_gh_attestation\\t%s\\n' "$gui_gh_attestation"
if command -v gh >/dev/null 2>&1 && gh auth status --hostname github.com >/dev/null 2>&1 || [ "$gui_gh_attestation" = yes ]; then printf 'gh_api\\tyes\\n'; else printf 'gh_api\\tno\\n'; fi
printf 'gh_protocol\\t%s\\n' "$(gh config get git_protocol --host github.com 2>/dev/null || true)"
if [ -f "$HOME/.config/gh/hosts.yml" ] && grep -q '^[[:space:]]*oauth_token:' "$HOME/.config/gh/hosts.yml"; then printf 'plaintext_oauth\\tyes\\n'; else printf 'plaintext_oauth\\tno\\n'; fi
ssh_output="$(ssh -n -o BatchMode=yes -o ConnectTimeout=10 -o ConnectionAttempts=1 -o StrictHostKeyChecking=yes -o IdentitiesOnly=yes -i "$key" -T git@github.com 2>&1 || true)"
case "$ssh_output" in *successfully\ authenticated*) printf 'github_ssh\\tyes\\n';; *) printf 'github_ssh\\tno\\n';; esac
'''


def parse_facts(text: str) -> dict[str, object]:
    facts: dict[str, object] = {}
    booleans = {
        "private_key",
        "public_key",
        "managed_config",
        "passphrase_free_exception",
        "passphrase_free_key",
        "effective_identity",
        "github_host_key",
        "native_agent",
        "agent_visible",
        "gui_gh_attestation",
        "gh_api",
        "plaintext_oauth",
        "github_ssh",
    }
    for line in text.splitlines():
        key, separator, value = line.partition("\t")
        if not separator:
            continue
        facts[key] = value == "yes" if key in booleans else value
    return facts


def audit_machine(machine: dict[str, Any], enrolled: list[dict[str, object]]) -> dict[str, object]:
    machine_id = str(machine.get("id"))
    result = target_run(machine, audit_script(machine_id))
    if result.returncode != 0:
        return {
            "machine_id": machine_id,
            "reachable": False,
            "error": (result.stderr or result.stdout).strip().splitlines()[-1][:300],
        }
    facts = parse_facts(result.stdout)
    fingerprint = facts.get("fingerprint")
    matching = [item for item in enrolled if item.get("fingerprint") == fingerprint]
    facts.update(
        {
            "reachable": True,
            "github_title": f"ctx9-fleet:{machine_id}",
            "github_enrolled": len(matching) == 1,
            "github_enrolled_title": matching[0].get("title") if len(matching) == 1 else None,
            "github_host_fingerprint": GITHUB_ED25519_FINGERPRINT,
        }
    )
    return facts


def provision_script(machine_id: str, *, passphrase_free: bool = False) -> str:
    key_name = f"id_ed25519_github_{machine_id}"
    exception_marker = "# ctx9-passphrase-free-linux-exception\n" if passphrase_free else ""
    agent_setting = "" if passphrase_free else "  AddKeysToAgent yes\n"
    config = f'''Host github.com
{exception_marker}  HostName github.com
  User git
  IdentityFile ~/.ssh/{key_name}
  IdentitiesOnly yes
{agent_setting}  StrictHostKeyChecking yes
'''
    return f'''set -eu
umask 077
key="$HOME/.ssh/{key_name}"
test -f "$key" && test -f "$key.pub"
identity_agent=""
if [ "$(uname -s)" = Linux ] && [ {"no" if passphrase_free else "yes"} = yes ]; then
  for candidate in "/run/user/$(id -u)/keyring/ssh" "/run/user/$(id -u)/gnupg/S.gpg-agent.ssh"; do
    if [ -S "$candidate" ]; then identity_agent="$candidate"; break; fi
  done
  test -n "$identity_agent"
fi
mkdir -p "$HOME/.ssh/config.d"
touch "$HOME/.ssh/config"
temporary_config="$(mktemp "$HOME/.ssh/config.XXXXXX")"
printf 'Include ~/.ssh/config.d/*\\n' > "$temporary_config"
grep -Ev '^[[:space:]]*Include[[:space:]]+~/.ssh/config.d/\\*[[:space:]]*$' "$HOME/.ssh/config" >> "$temporary_config" || true
mv "$temporary_config" "$HOME/.ssh/config"
cat > "$HOME/.ssh/config.d/ctx9-github.conf" <<'CTX9_CONFIG'
{config}CTX9_CONFIG
if [ "$(uname -s)" = Darwin ]; then printf '  UseKeychain yes\\n' >> "$HOME/.ssh/config.d/ctx9-github.conf"; fi
if [ -n "$identity_agent" ]; then printf '  IdentityAgent %s\\n' "$identity_agent" >> "$HOME/.ssh/config.d/ctx9-github.conf"; fi
touch "$HOME/.ssh/known_hosts"
grep -Fqx {shlex.quote(GITHUB_ED25519_HOST_KEY)} "$HOME/.ssh/known_hosts" || printf '%s\\n' {shlex.quote(GITHUB_ED25519_HOST_KEY)} >> "$HOME/.ssh/known_hosts"
chmod 700 "$HOME/.ssh" "$HOME/.ssh/config.d"
chmod 600 "$HOME/.ssh/config" "$HOME/.ssh/config.d/ctx9-github.conf" "$HOME/.ssh/known_hosts" "$key"
chmod 644 "$key.pub"
gh config set git_protocol ssh --host github.com
'''


def interactive_generate(machine: dict[str, Any]) -> None:
    machine_id = str(machine["id"])
    key = f"$HOME/.ssh/id_ed25519_github_{machine_id}"
    command = (
        "umask 077; mkdir -p \"$HOME/.ssh\"; "
        f"test ! -e \"{key}\" && ssh-keygen -t ed25519 -a 100 -f \"{key}\" "
        f"-C {shlex.quote('ctx9-fleet:' + machine_id)}; "
        "if [ \"$(uname -s)\" = Darwin ]; then "
        f"ssh-add --apple-use-keychain \"{key}\"; "
        "else agent=\"\"; "
        "for candidate in \"/run/user/$(id -u)/keyring/ssh\" \"/run/user/$(id -u)/gnupg/S.gpg-agent.ssh\"; do "
        "if [ -S \"$candidate\" ]; then agent=\"$candidate\"; break; fi; done; "
        "test -n \"$agent\"; "
        f"SSH_AUTH_SOCK=\"$agent\" ssh-add \"{key}\"; fi"
    )
    if machine.get("transport") == "local":
        completed = subprocess.run(["/bin/sh", "-c", command], check=False)
    else:
        completed = subprocess.run(
            ["ssh", "-t", str(machine["ssh_alias"]), command], check=False
        )
    if completed.returncode != 0:
        raise FleetAuthError(f"interactive key generation failed on {machine_id}")


def passphrase_free_generation_script(machine_id: str) -> str:
    """Preserve any prior keypair and generate the approved Linux exception locally."""
    key_name = f"id_ed25519_github_{machine_id}"
    return f'''set -eu
[ "$(uname -s)" = Linux ]
umask 077
key="$HOME/.ssh/{key_name}"
mkdir -p "$HOME/.ssh"
if [ -f "$key" ] && ssh-keygen -y -P '' -f "$key" >/dev/null 2>&1; then
  test -f "$key.pub"
else
  if [ -e "$key" ] || [ -e "$key.pub" ]; then
    stamp="$(date -u +%Y%m%dT%H%M%SZ)"
    backup="$HOME/.ssh/ctx9-key-backups/$stamp"
    mkdir -p "$backup"
    [ ! -e "$key" ] || mv "$key" "$backup/"
    [ ! -e "$key.pub" ] || mv "$key.pub" "$backup/"
    chmod 700 "$HOME/.ssh/ctx9-key-backups" "$backup"
  fi
  ssh-keygen -q -t ed25519 -a 100 -N '' -f "$key" -C {shlex.quote('ctx9-fleet:' + machine_id)}
fi
chmod 600 "$key"
chmod 644 "$key.pub"
'''


def public_key(machine: dict[str, Any]) -> str:
    machine_id = str(machine["id"])
    script = f'cat "$HOME/.ssh/id_ed25519_github_{machine_id}.pub"'
    result = target_run(machine, script)
    if result.returncode != 0 or not output(result):
        raise FleetAuthError(f"dedicated public key is missing on {machine_id}")
    return output(result)


def command_audit(machines: list[dict[str, Any]], *, json_output: bool) -> int:
    enrolled = github_keys()
    reports = [audit_machine(machine, enrolled) for machine in machines]
    if json_output:
        print(json.dumps(reports, indent=2, sort_keys=True))
    else:
        for report in reports:
            print(
                f"{report.get('machine_id')}: reachable={report.get('reachable')} "
                f"key={report.get('fingerprint') or 'missing'} enrolled={report.get('github_enrolled')} "
                f"ssh={report.get('github_ssh')} gh_api={report.get('gh_api')} "
                f"protocol={report.get('gh_protocol') or 'unknown'}"
            )
    return 0 if all(report.get("reachable") for report in reports) else 2


def command_provision(
    machines: list[dict[str, Any]],
    *,
    apply: bool,
    interactive: bool,
    allow_passphrase_free: bool = False,
) -> int:
    if interactive and (not apply or len(machines) != 1):
        raise FleetAuthError("--interactive requires --apply and exactly one target")
    if interactive and allow_passphrase_free:
        raise FleetAuthError("--interactive and --allow-passphrase-free are mutually exclusive")
    enrolled = github_keys() if allow_passphrase_free else []
    for machine in machines:
        report = audit_machine(machine, enrolled)
        print(
            f"{machine['id']}: would ensure dedicated key, pinned GitHub host key, "
            "managed SSH config, and gh git_protocol=ssh"
        )
        if allow_passphrase_free:
            if report.get("platform") != "Linux":
                raise FleetAuthError("--allow-passphrase-free is restricted to registered Linux machines")
            if report.get("github_enrolled") and not report.get("passphrase_free_key"):
                raise FleetAuthError(
                    f"{machine['id']}'s current key is enrolled; rotate it through a separately approved revocation workflow"
                )
            print(
                f"{machine['id']}: approved Linux exception would preserve any passphrased keypair, "
                "generate a passphrase-free replacement locally, and mark managed SSH config"
            )
        if not apply:
            continue
        if allow_passphrase_free:
            generated = target_run(
                machine, passphrase_free_generation_script(str(machine["id"]))
            )
            if generated.returncode != 0:
                raise FleetAuthError(
                    f"passphrase-free key generation failed on {machine['id']}: "
                    f"{(generated.stderr or generated.stdout).strip()[-300:]}"
                )
        elif not report.get("private_key"):
            if not interactive:
                raise FleetAuthError(
                    f"{machine['id']} needs passphrase-protected target-local key generation; "
                    "rerun for this single target with --apply --interactive"
                )
            if not report.get("native_agent"):
                raise FleetAuthError(
                    f"{machine['id']}'s native SSH agent is unavailable in this session; "
                    "run the same command in the target's logged-in GUI Terminal during onboarding"
                )
            interactive_generate(machine)
        result = target_run(
            machine,
            provision_script(
                str(machine["id"]), passphrase_free=allow_passphrase_free
            ),
        )
        if result.returncode != 0:
            raise FleetAuthError(
                f"provisioning failed on {machine['id']}: {(result.stderr or result.stdout).strip()[-300:]}"
            )
    if not apply:
        print("DRY RUN: no target or GitHub account changes made")
    return 0


def command_enroll(
    machines: list[dict[str, Any]], *, apply: bool, approve_fingerprint: str | None
) -> int:
    if len(machines) != 1:
        raise FleetAuthError("enroll requires exactly one --target")
    machine = machines[0]
    key = public_key(machine)
    fingerprint = public_key_fingerprint(key)
    title = f"ctx9-fleet:{machine['id']}"
    enrolled = github_keys()
    existing = [item for item in enrolled if item.get("fingerprint") == fingerprint]
    print(f"machine: {machine['id']}")
    print(f"title: {title}")
    print(f"fingerprint: {fingerprint}")
    if existing:
        print(f"already enrolled as: {existing[0].get('title')}")
        return 0
    if not apply:
        print("DRY RUN: approval and --apply are required before public-key enrollment")
        return 0
    if approve_fingerprint != fingerprint:
        raise FleetAuthError("--approve-fingerprint must exactly match the previewed fingerprint")
    temporary_path = ""
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            handle.write(key + "\n")
            temporary_path = handle.name
        os.chmod(temporary_path, 0o600)
        result = run(
            [
                "gh",
                "ssh-key",
                "add",
                temporary_path,
                "--type",
                "authentication",
                "--title",
                title,
            ]
        )
    finally:
        if temporary_path:
            Path(temporary_path).unlink(missing_ok=True)
    if result.returncode != 0:
        raise FleetAuthError(f"GitHub enrollment failed: {(result.stderr or result.stdout).strip()[-300:]}")
    print("public authentication key enrolled; private key remained on the target")
    return 0


def command_verify(machines: list[dict[str, Any]], *, json_output: bool) -> int:
    enrolled = github_keys()
    reports = [audit_machine(machine, enrolled) for machine in machines]
    required = (
        "private_key",
        "public_key",
        "managed_config",
        "effective_identity",
        "github_host_key",
        "gh_api",
        "github_ssh",
        "github_enrolled",
    )
    for report in reports:
        custody_ready = bool(
            report.get("native_agent") and report.get("agent_visible")
        ) or bool(
            report.get("platform") == "Linux"
            and report.get("passphrase_free_exception")
            and report.get("passphrase_free_key")
        )
        report["accepted"] = bool(
            report.get("reachable")
            and all(report.get(key) is True for key in required)
            and custody_ready
            and report.get("gh_protocol") == "ssh"
            and report.get("plaintext_oauth") is False
        )
    if json_output:
        print(json.dumps(reports, indent=2, sort_keys=True))
    else:
        for report in reports:
            print(f"{report.get('machine_id')}: accepted={report.get('accepted')}")
    return 0 if all(report["accepted"] for report in reports) else 2


def command_revoke(
    machines: list[dict[str, Any]], *, apply: bool, approve_title: str | None
) -> int:
    if len(machines) != 1:
        raise FleetAuthError("revoke requires exactly one --target")
    machine = machines[0]
    title = f"ctx9-fleet:{machine['id']}"
    matching = [item for item in github_keys() if item.get("title") == title]
    print(f"would revoke GitHub authentication key titled {title}")
    if not matching:
        print("no matching enrolled key exists")
        return 0
    if not apply:
        print("DRY RUN: no GitHub account changes made")
        return 0
    if approve_title != title:
        raise FleetAuthError(f"--approve-title must exactly equal {title}")
    result = run(["gh", "api", "--method", "DELETE", f"user/keys/{matching[0]['id']}"])
    if result.returncode != 0:
        raise FleetAuthError(f"GitHub key revocation failed: {(result.stderr or result.stdout).strip()[-300:]}")
    print("GitHub public key revoked; target-local files were preserved")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("audit", "verify"):
        command = subparsers.add_parser(name)
        command.add_argument("--target", action="append", default=[])
        command.add_argument("--json", action="store_true")
    provision = subparsers.add_parser("provision")
    provision.add_argument("--target", action="append", default=[])
    provision.add_argument("--apply", action="store_true")
    provision.add_argument("--interactive", action="store_true")
    provision.add_argument(
        "--allow-passphrase-free",
        action="store_true",
        help="use the explicitly approved unattended Linux machine-key exception",
    )
    enroll = subparsers.add_parser("enroll")
    enroll.add_argument("--target", action="append", default=[])
    enroll.add_argument("--apply", action="store_true")
    enroll.add_argument("--approve-fingerprint")
    revoke = subparsers.add_parser("revoke")
    revoke.add_argument("--target", action="append", default=[])
    revoke.add_argument("--apply", action="store_true")
    revoke.add_argument("--approve-title")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        root = vault_root()
        registry = load_registry((args.registry or root / REGISTRY_RELATIVE).expanduser().resolve())
        source_id = current_machine_id(root)
        machines = resolve_machines(registry, args.target, source_id)
        machines = [
            {**machine, "transport": "local"}
            if machine.get("id") == source_id
            else machine
            for machine in machines
        ]
        if args.command in {"enroll", "revoke"} and source_id != registry.get(
            "primary_machine_id"
        ):
            raise FleetAuthError("GitHub account key enrollment and revocation must run on the registered primary")
        if (
            args.command == "provision"
            and args.allow_passphrase_free
            and source_id != registry.get("primary_machine_id")
        ):
            raise FleetAuthError("approved passphrase-free Linux provisioning must run on the registered primary")
        if args.command == "audit":
            return command_audit(machines, json_output=args.json)
        if args.command == "provision":
            return command_provision(
                machines,
                apply=args.apply,
                interactive=args.interactive,
                allow_passphrase_free=args.allow_passphrase_free,
            )
        if args.command == "enroll":
            return command_enroll(machines, apply=args.apply, approve_fingerprint=args.approve_fingerprint)
        if args.command == "verify":
            return command_verify(machines, json_output=args.json)
        if args.command == "revoke":
            return command_revoke(machines, apply=args.apply, approve_title=args.approve_title)
    except (FleetAuthError, OSError, subprocess.SubprocessError) as exc:
        print(f"GitHub fleet authentication failed: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
