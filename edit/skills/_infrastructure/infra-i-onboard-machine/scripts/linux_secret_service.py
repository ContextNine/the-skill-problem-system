#!/usr/bin/env python3
"""Create, unlock, repair, and verify the Linux Login Secret Service collection."""

from __future__ import annotations

import getpass
import os
import subprocess
import sys
import time


SERVICE_NAME = "org.freedesktop.secrets"
ROOT_PATH = "/org/freedesktop/secrets"
LOGIN_PATH = "/org/freedesktop/secrets/collection/login"
SERVICE_INTERFACE = "org.freedesktop.Secret.Service"
INTERNAL_INTERFACE = "org.gnome.keyring.InternalUnsupportedGuiltRiddenInterface"
PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"
COLLECTION_INTERFACE = "org.freedesktop.Secret.Collection"


def configure_session_bus() -> None:
    runtime_dir = os.environ.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    os.environ.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={runtime_dir}/bus")


def collection_properties(bus: object, dbus: object, path: str) -> object | None:
    try:
        properties = dbus.Interface(
            bus.get_object(SERVICE_NAME, path), PROPERTIES_INTERFACE
        )
        properties.Get(COLLECTION_INTERFACE, "Locked", timeout=10)
        return properties
    except dbus.DBusException as exc:
        if exc.get_dbus_name() in {
            "org.freedesktop.DBus.Error.UnknownMethod",
            "org.freedesktop.DBus.Error.UnknownObject",
        }:
            return None
        raise


def verify_secret_service() -> None:
    probe = f"ctx9-secret-service-{int(time.time())}"
    subprocess.run(
        [
            "secret-tool",
            "store",
            "--label=ctx9 Secret Service verification",
            "ctx9-probe",
            probe,
        ],
        input=b"available",
        check=True,
        timeout=10,
    )
    try:
        value = subprocess.check_output(
            ["secret-tool", "lookup", "ctx9-probe", probe], timeout=10
        ).strip()
    finally:
        subprocess.run(
            ["secret-tool", "clear", "ctx9-probe", probe],
            check=False,
            timeout=10,
        )
    if value != b"available":
        raise RuntimeError("Secret Service store/read verification failed")


def main() -> int:
    if not sys.stdin.isatty():
        print(
            "ERROR: run this installed script from a standalone interactive SSH TTY; "
            "do not feed its SSH command with a pipe, heredoc, or here-string",
            file=sys.stderr,
        )
        return 2

    configure_session_bus()
    try:
        import dbus
    except ImportError:
        print("ERROR: target requires the python3-dbus package", file=sys.stderr)
        return 2

    bus = dbus.SessionBus()
    root = bus.get_object(SERVICE_NAME, ROOT_PATH)
    service = dbus.Interface(root, SERVICE_INTERFACE)
    internal = dbus.Interface(root, INTERNAL_INTERFACE)
    alias_path = str(service.ReadAlias("default", timeout=10))
    collection_path = alias_path if alias_path != "/" else LOGIN_PATH
    properties = collection_properties(bus, dbus, collection_path)

    if properties is not None and not bool(
        properties.Get(COLLECTION_INTERFACE, "Locked", timeout=10)
    ):
        verify_secret_service()
        print("Managed Login keyring is already unlocked")
        return 0

    password = getpass.getpass("Login keyring password: ")
    if "\n" in password or "\r" in password:
        print("ERROR: keyring password may not contain line endings", file=sys.stderr)
        return 2
    clean_password = password.encode()
    password = None

    _output, session_path = service.OpenSession(
        "plain", dbus.String("", variant_level=1), timeout=10
    )

    def make_secret(value: bytes) -> object:
        return dbus.Struct(
            (
                dbus.ObjectPath(session_path),
                dbus.ByteArray(b""),
                dbus.ByteArray(value),
                dbus.String("text/plain"),
            ),
            signature="oayays",
        )

    if properties is None:
        attributes = dbus.Dictionary(
            {
                "org.freedesktop.Secret.Collection.Label": dbus.String(
                    "Login", variant_level=1
                )
            },
            signature="sv",
        )
        collection_path = str(
            internal.CreateWithMasterPassword(
                attributes, make_secret(clean_password), timeout=10
            )
        )
        service.SetAlias("default", dbus.ObjectPath(collection_path), timeout=10)
        result = "created and unlocked"
    else:
        try:
            internal.UnlockWithMasterPassword(
                dbus.ObjectPath(collection_path), make_secret(clean_password), timeout=10
            )
            result = "unlocked"
        except dbus.DBusException:
            accidental_password = clean_password + b"\n"
            try:
                internal.UnlockWithMasterPassword(
                    dbus.ObjectPath(collection_path),
                    make_secret(accidental_password),
                    timeout=10,
                )
                internal.ChangeWithMasterPassword(
                    dbus.ObjectPath(collection_path),
                    make_secret(accidental_password),
                    make_secret(clean_password),
                    timeout=10,
                )
                result = "unlocked; accidental trailing newline removed"
            except dbus.DBusException:
                print("ERROR: Login keyring password was not accepted", file=sys.stderr)
                return 1

    properties = collection_properties(bus, dbus, collection_path)
    if properties is None or bool(
        properties.Get(COLLECTION_INTERFACE, "Locked", timeout=10)
    ):
        print("ERROR: Login keyring remains locked", file=sys.stderr)
        return 1
    verify_secret_service()
    print(f"Managed Login keyring {result}; Secret Service verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
