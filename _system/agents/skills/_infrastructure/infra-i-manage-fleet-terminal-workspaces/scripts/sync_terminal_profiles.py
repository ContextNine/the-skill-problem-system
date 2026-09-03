#!/usr/bin/env python3
"""Install and verify managed tmux, btop, and Starship fleet profiles."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any


PROFILES: dict[str, dict[str, Any]] = {}
PLUGIN_PINS = {
    "tmux-resurrect": ("https://github.com/tmux-plugins/tmux-resurrect.git", "cff343cf9e81983d3da0c8562b01616f12e8d548"),
    "tmux-continuum": ("https://github.com/tmux-plugins/tmux-continuum.git", "0698e8f4b17d6454c71bf5212895ec055c578da0"),
    "tmux-cpu": ("https://github.com/tmux-plugins/tmux-cpu.git", "bcb110d754ab2417de824c464730c412a3eb2769"),
}
MARKER_START = "# >>> workmux starship >>>"
MARKER_END = "# <<< workmux starship <<<"
MARKER_BODY = """# >>> workmux starship >>>
export PATH="$HOME/.local/bin:$PATH"
export STARSHIP_CONFIG="$HOME/.config/starship.toml"
if command -v starship >/dev/null 2>&1; then
  eval "$(starship init __SHELL__)"
fi
# <<< workmux starship <<<"""


def run(argv: list[str], *, check: bool = True, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check, timeout=timeout)


def skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_inventory() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "_system/agents/_package/instance/fleet/machines.json"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("private machine registry not found from skill path")


def load_inventory(path: Path) -> dict[str, Any]:
    data = json.loads(path.expanduser().read_text(encoding="utf-8"))
    if data.get("schema_version") != 6 or not isinstance(data.get("machines"), list):
        raise ValueError("inventory schema_version must be 6 and contain machines")
    for machine in data["machines"]:
        if machine.get("transport") not in {"local", "ssh"}:
            raise ValueError(f"unsupported transport for {machine.get('id', '<unnamed>')}")
        if machine.get("transport") == "ssh" and not machine.get("ssh_alias"):
            raise ValueError(f"ssh_alias missing for {machine.get('id', '<unnamed>')}")
        home = PurePosixPath(machine.get("home", ""))
        if not home.is_absolute() or any(char.isspace() for char in str(home)):
            raise ValueError(f"unsafe home path for {machine.get('id', '<unnamed>')}")
    return data


def profiles_from_inventory(inventory: dict[str, Any]) -> dict[str, dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}
    for machine in inventory["machines"]:
        terminal = machine.get("terminal_profile")
        if not isinstance(terminal, dict):
            continue
        profile = dict(terminal)
        if isinstance(profile.get("link_brew_commands"), list):
            profile["link_brew_commands"] = tuple(profile["link_brew_commands"])
        profile["name"] = machine["display_name"]
        profiles[machine["id"]] = profile
    return profiles


PROFILES = profiles_from_inventory(load_inventory(default_inventory()))


def select_devices(
    inventory: dict[str, Any],
    requested: set[str] | None = None,
    *,
    provision_disabled: bool = False,
) -> list[dict[str, Any]]:
    fleet = [m for m in inventory["machines"] if m.get("id") in PROFILES]
    eligible = [m for m in fleet if m.get("enabled")]
    if requested is None:
        if provision_disabled:
            raise ValueError("--provision-disabled requires at least one explicit --target")
        return eligible
    folded = {value.casefold() for value in requested}
    known = {value.casefold() for m in fleet for value in (m["id"], m["display_name"])}
    unknown = sorted(value for value in requested if value.casefold() not in known)
    if unknown:
        raise ValueError("unknown target machines: " + ", ".join(unknown))
    disabled = [m["id"] for m in fleet if (m["id"].casefold() in folded or m["display_name"].casefold() in folded) and not m.get("enabled")]
    if disabled and not provision_disabled:
        raise ValueError("target machines disabled in inventory: " + ", ".join(disabled))
    candidates = fleet if provision_disabled else eligible
    return [m for m in candidates if m["id"].casefold() in folded or m["display_name"].casefold() in folded]


def render_starship(machine_id: str, template: str) -> str:
    profile = PROFILES[machine_id]
    return template.replace("__MACHINE_NAME__", profile["name"]).replace("__ACCENT__", profile["accent"])


def render_workmux(machine_id: str, template: str) -> str:
    return template.replace("__DEFAULT_SESSION__", machine_id)


def update_marker(text: str, shell_name: str) -> str:
    block = MARKER_BODY.replace("__SHELL__", shell_name)
    start = text.find(MARKER_START)
    end = text.find(MARKER_END)
    if (start == -1) != (end == -1) or (start != -1 and end < start):
        raise ValueError("malformed workmux Starship marker block")
    if start != -1:
        end += len(MARKER_END)
        prefix = text[:start].rstrip()
        updated = (prefix + "\n\n" if prefix else "") + block + text[end:]
    else:
        updated = text.rstrip() + ("\n\n" if text.strip() else "") + block + "\n"
    return updated if updated.endswith("\n") else updated + "\n"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Host:
    def __init__(self, machine: dict[str, Any]):
        self.machine = machine
        self.home = machine["home"]

    def command(self, script: str, *, check: bool = True, timeout: int = 600) -> subprocess.CompletedProcess[str]:
        if self.machine["transport"] == "local":
            return run(["/bin/sh", "-lc", script], check=check, timeout=timeout)
        return run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", self.machine["ssh_alias"], script], check=check, timeout=timeout)

    def read(self, path: str) -> bytes | None:
        result = self.command(f"test -f {shlex.quote(path)} && cat {shlex.quote(path)}", check=False)
        if result.returncode != 0:
            return None
        return result.stdout.encode()

    def deploy(self, path: str, data: bytes, mode: int, stamp: str) -> None:
        parent = str(PurePosixPath(path).parent)
        temporary = path + ".workmux-new"
        backup = path + ".backup-" + stamp
        if self.machine["transport"] == "local":
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                target.replace(Path(backup))
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
                handle.write(data)
                temp_path = Path(handle.name)
            temp_path.chmod(mode)
            os.replace(temp_path, target)
            return
        self.command(f"mkdir -p {shlex.quote(parent)} && test ! -e {shlex.quote(temporary)}")
        with tempfile.NamedTemporaryFile(delete=False) as handle:
            handle.write(data)
            source = Path(handle.name)
        try:
            run(["scp", "-q", str(source), f"{self.machine['ssh_alias']}:{temporary}"])
        finally:
            source.unlink(missing_ok=True)
        self.command(
            f"if test -f {shlex.quote(path)}; then mv {shlex.quote(path)} {shlex.quote(backup)}; fi; "
            f"chmod {mode:o} {shlex.quote(temporary)} && mv {shlex.quote(temporary)} {shlex.quote(path)}"
        )


def desired_files(machine: dict[str, Any]) -> list[tuple[str, bytes, int]]:
    assets = skill_root() / "assets/terminal-workspaces"
    tmux = (assets / "tmux.conf").read_bytes()
    starship = render_starship(machine["id"], (assets / "starship.toml.template").read_text()).encode()
    workmux = render_workmux(machine["id"], (assets / "workmux").read_text()).encode()
    btop_control = render_workmux(machine["id"], (assets / "workmux-btop-control").read_text()).encode()
    branch = (assets / "workmux-git-branch").read_bytes()
    home = PurePosixPath(machine["home"])
    return [
        (str(home / ".tmux.conf"), tmux, 0o644),
        (str(home / ".config/starship.toml"), starship, 0o644),
        (str(home / ".local/bin/workmux"), workmux, 0o755),
        (str(home / ".local/bin/workmux-btop-control"), btop_control, 0o755),
        (str(home / ".local/bin/workmux-git-branch"), branch, 0o755),
    ]


def missing_commands(host: Host) -> list[str]:
    result = host.command(
        'PATH="$HOME/.local/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"; export PATH; '
        'for c in tmux btop starship git; do command -v "$c" >/dev/null 2>&1 || printf \'%s\\n\' "$c"; done'
    )
    return result.stdout.split()


def install_packages(host: Host, machine_id: str, missing: list[str]) -> None:
    packages = [name for name in missing if name in {"tmux", "btop", "starship"}]
    if not packages:
        return
    profile = PROFILES[machine_id]
    btop_prebuilt = profile.get("btop_prebuilt")
    if btop_prebuilt and "btop" in packages:
        packages.remove("btop")
        install_prebuilt_btop(host, btop_prebuilt)
    prebuilt = profile.get("starship_prebuilt")
    if prebuilt and "starship" in packages:
        packages.remove("starship")
        install_prebuilt_starship(host, prebuilt)
    if not packages:
        return
    quoted = " ".join(shlex.quote(name) for name in packages)
    if profile.get("package_manager") == "apt":
        host.command(f"sudo -n apt-get update && sudo -n apt-get install -y {quoted}", check=True, timeout=1800)
    else:
        brew = shlex.quote(profile["brew"])
        # Older supported macOS releases may compile Homebrew dependencies.
        host.command(f"{brew} install {quoted}", check=True, timeout=7200)


def install_prebuilt_starship(host: Host, release: dict[str, str]) -> None:
    """Install pinned official binary without invoking Homebrew on legacy macOS."""
    url = shlex.quote(release["url"])
    digest = shlex.quote(release["sha256"])
    host.command(
        "tmp_dir=$(mktemp -d /tmp/workmux-starship.XXXXXX) && "
        "trap 'rm -rf \"$tmp_dir\"' EXIT HUP INT TERM && "
        f"curl --fail --location --silent --show-error {url} -o \"$tmp_dir/starship.tar.gz\" && "
        f"test \"$(shasum -a 256 \"$tmp_dir/starship.tar.gz\" | awk '{{print $1}}')\" = {digest} && "
        "tar -xzf \"$tmp_dir/starship.tar.gz\" -C \"$tmp_dir\" starship && "
        "test -x \"$tmp_dir/starship\" && mkdir -p \"$HOME/.local/bin\" && "
        "chmod 755 \"$tmp_dir/starship\" && mv \"$tmp_dir/starship\" \"$HOME/.local/bin/starship\"",
        timeout=600,
    )


def install_prebuilt_btop(host: Host, release: dict[str, str]) -> None:
    """Install checksum-pinned Monterey bottles without compiling LLVM."""
    version = shlex.quote(release["version"])
    btop_url = shlex.quote(release["url"])
    btop_digest = shlex.quote(release["sha256"])
    gcc_url = shlex.quote(release["gcc_url"])
    gcc_digest = shlex.quote(release["gcc_sha256"])
    host.command(
        "tmp_dir=$(mktemp -d /tmp/workmux-btop.XXXXXX) && "
        "trap 'rm -rf \"$tmp_dir\"' EXIT HUP INT TERM && "
        "mkdir \"$tmp_dir/btop-root\" \"$tmp_dir/gcc-root\" && "
        "btop_token=$(curl --fail --silent --show-error 'https://ghcr.io/token?scope=repository:homebrew/core/btop:pull' | sed -E 's/.*\"token\":\"([^\"]+)\".*/\\1/') && "
        "gcc_token=$(curl --fail --silent --show-error 'https://ghcr.io/token?scope=repository:homebrew/core/gcc:pull' | sed -E 's/.*\"token\":\"([^\"]+)\".*/\\1/') && "
        f"curl --fail --location --silent --show-error -H \"Authorization: Bearer $btop_token\" {btop_url} -o \"$tmp_dir/btop.tar.gz\" && "
        f"curl --fail --location --silent --show-error -H \"Authorization: Bearer $gcc_token\" {gcc_url} -o \"$tmp_dir/gcc.tar.gz\" && "
        f"test \"$(shasum -a 256 \"$tmp_dir/btop.tar.gz\" | awk '{{print $1}}')\" = {btop_digest} && "
        f"test \"$(shasum -a 256 \"$tmp_dir/gcc.tar.gz\" | awk '{{print $1}}')\" = {gcc_digest} && "
        "tar -xzf \"$tmp_dir/btop.tar.gz\" -C \"$tmp_dir/btop-root\" && "
        "tar -xzf \"$tmp_dir/gcc.tar.gz\" -C \"$tmp_dir/gcc-root\" && "
        f"target=\"$HOME/.local/share/workmux/btop/{version}\" && new=\"$target.workmux-new\" && "
        "rm -rf \"$new\" && mkdir -p \"$new/lib\" \"$HOME/.local/bin\" && "
        f"cp -R \"$tmp_dir/btop-root/btop/{version}/\"* \"$new/\" && "
        "cp \"$tmp_dir/gcc-root/gcc/13.2.0/lib/gcc/current/libstdc++.6.dylib\" \"$new/lib/\" && "
        "cp \"$tmp_dir/gcc-root/gcc/13.2.0/lib/gcc/current/libgcc_s.1.1.dylib\" \"$new/lib/\" && "
        "install_name_tool -change '@@HOMEBREW_PREFIX@@/opt/gcc/lib/gcc/current/libstdc++.6.dylib' '@executable_path/../lib/libstdc++.6.dylib' \"$new/bin/btop\" && "
        "install_name_tool -change '@@HOMEBREW_PREFIX@@/opt/gcc/lib/gcc/current/libgcc_s.1.1.dylib' '@executable_path/../lib/libgcc_s.1.1.dylib' \"$new/bin/btop\" && "
        "install_name_tool -change '@rpath/libgcc_s.1.1.dylib' '@loader_path/libgcc_s.1.1.dylib' \"$new/lib/libstdc++.6.dylib\" && "
        "chmod 755 \"$new/bin/btop\" && \"$new/bin/btop\" --version >/dev/null && "
        "mkdir -p \"$(dirname \"$target\")\" && "
        "if test -e \"$target\"; then mv \"$target\" \"$target.backup-$(date -u +%Y%m%dT%H%M%SZ)\"; fi && "
        "mv \"$new\" \"$target\" && ln -sfn \"$target/bin/btop\" \"$HOME/.local/bin/btop\"",
        timeout=1800,
    )


def link_brew_commands(host: Host, machine_id: str, stamp: str) -> None:
    profile = PROFILES[machine_id]
    commands = profile.get("link_brew_commands")
    if not commands:
        return
    brew_bin = str(PurePosixPath(profile["brew"]).parent)
    script = ["mkdir -p \"$HOME/.local/bin\""]
    for command in commands:
        source = f"{brew_bin}/{command}"
        target = f"$HOME/.local/bin/{command}"
        script.append(f"test -e {shlex.quote(source)}")
        script.append(f"if test -e \"{target}\" && ! test \"$(readlink \"{target}\" 2>/dev/null || true)\" = {shlex.quote(source)}; then mv \"{target}\" \"{target}.backup-{stamp}\"; fi")
        script.append(f"ln -sfn {shlex.quote(source)} \"{target}\"")
    host.command("; ".join(script))


def verify_prebuilt_versions(host: Host, machine_id: str) -> list[str]:
    profile = PROFILES[machine_id]
    failures: list[str] = []
    for command, profile_key in (("btop", "btop_prebuilt"), ("starship", "starship_prebuilt")):
        release = profile.get(profile_key)
        if not release:
            continue
        result = host.command(
            f'PATH="$HOME/.local/bin:/usr/local/bin:$PATH"; {command} --version',
            check=False,
        )
        if result.returncode != 0 or release["version"] not in result.stdout:
            failures.append(f"{command} prebuilt version mismatch")
    return failures


def plugin_head(host: Host, machine: dict[str, Any], name: str) -> str | None:
    path = str(PurePosixPath(machine["home"]) / ".local/share/workmux/plugins" / name)
    result = host.command(f"git -C {shlex.quote(path)} rev-parse HEAD", check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def install_plugin(host: Host, machine: dict[str, Any], name: str, stamp: str) -> None:
    url, commit = PLUGIN_PINS[name]
    root = str(PurePosixPath(machine["home"]) / ".local/share/workmux/plugins")
    target = str(PurePosixPath(root) / name)
    temporary = target + ".workmux-new"
    backup = target + ".backup-" + stamp
    host.command(
        f"mkdir -p {shlex.quote(root)} && test ! -e {shlex.quote(temporary)} && "
        f"git clone --quiet --filter=blob:none {shlex.quote(url)} {shlex.quote(temporary)} && "
        f"git -C {shlex.quote(temporary)} checkout --quiet {shlex.quote(commit)} && "
        f"test \"$(git -C {shlex.quote(temporary)} rev-parse HEAD)\" = {shlex.quote(commit)} && "
        f"if test -e {shlex.quote(target)}; then mv {shlex.quote(target)} {shlex.quote(backup)}; fi && "
        f"mv {shlex.quote(temporary)} {shlex.quote(target)}"
    )


def configure_machine(machine: dict[str, Any], *, apply: bool, verify: bool, stamp: str) -> bool:
    machine_id = machine["id"]
    host = Host(machine)
    failures: list[str] = []
    missing = missing_commands(host)
    if "git" in missing and (apply or verify):
        failures.append("git missing")
    package_missing = [name for name in missing if name in {"tmux", "btop", "starship"}]
    if package_missing:
        print(f"{machine_id}: packages missing: {','.join(package_missing)}")
        if apply:
            install_packages(host, machine_id, package_missing)
            link_brew_commands(host, machine_id, stamp)
            package_missing = [name for name in missing_commands(host) if name in {"tmux", "btop", "starship"}]
        if package_missing and (apply or verify):
            failures.append("commands missing: " + ",".join(package_missing))
    elif apply:
        link_brew_commands(host, machine_id, stamp)

    if apply or verify:
        failures.extend(verify_prebuilt_versions(host, machine_id))

    for path, data, mode in desired_files(machine):
        actual = host.read(path)
        if actual == data:
            print(f"{machine_id}: match {path}")
        else:
            print(f"{machine_id}: {'missing' if actual is None else 'different'} {path}")
            if apply:
                host.deploy(path, data, mode, stamp)
                if host.read(path) != data:
                    failures.append(f"post-install mismatch: {path}")
            elif verify:
                failures.append(f"config mismatch: {path}")

    profile = PROFILES[machine_id]
    rc_path = str(PurePosixPath(machine["home"]) / profile["shell_rc"])
    existing = (host.read(rc_path) or b"").decode(errors="replace")
    shell_name = "bash" if profile["shell_rc"] == ".bashrc" else "zsh"
    wanted_rc = update_marker(existing, shell_name).encode()
    if existing.encode() != wanted_rc:
        print(f"{machine_id}: shell marker different {rc_path}")
        if apply:
            host.deploy(rc_path, wanted_rc, 0o644, stamp)
        elif verify:
            failures.append("shell marker mismatch")
    else:
        print(f"{machine_id}: shell marker match")

    for name, (_, expected) in PLUGIN_PINS.items():
        actual = plugin_head(host, machine, name)
        if actual == expected:
            print(f"{machine_id}: plugin {name} pinned")
            continue
        print(f"{machine_id}: plugin {name} {'missing' if actual is None else actual[:12]} -> {expected[:12]}")
        if apply:
            install_plugin(host, machine, name, stamp)
            if plugin_head(host, machine, name) != expected:
                failures.append(f"plugin mismatch: {name}")
        elif verify:
            failures.append(f"plugin mismatch: {name}")

    if apply and not failures:
        result = host.command(
            'PATH="$HOME/.local/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"; export PATH; '
            "tmux -L workmux-verify -f \"$HOME/.tmux.conf\" new-session -d -s verify && "
            "tmux -L workmux-verify display-message -p -t verify '#S'; task_status=$?; "
            'tmux -L workmux-verify kill-server >/dev/null 2>&1 || true; exit $task_status',
            check=False,
        )
        if result.returncode != 0:
            failures.append("tmux config load failed: " + result.stderr.strip())
    for failure in failures:
        print(f"{machine_id}: FAIL {failure}")
    return not failures


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--inventory", type=Path)
    result.add_argument("--target", action="append", default=[])
    result.add_argument(
        "--provision-disabled",
        action="store_true",
        help="configure explicitly named disabled machines before fleet enablement",
    )
    mode = result.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--verify", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    inventory = load_inventory(args.inventory or default_inventory())
    machines = select_devices(
        inventory,
        set(args.target) if args.target else None,
        provision_disabled=args.provision_disabled,
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    print("mode=" + ("apply" if args.apply else "verify" if args.verify else "dry-run"))
    print("targets=" + ",".join(machine["id"] for machine in machines))
    okay = True
    for machine in machines:
        okay = configure_machine(machine, apply=args.apply, verify=args.verify, stamp=stamp) and okay
    return 0 if okay or (not args.apply and not args.verify) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        raise SystemExit(2)
