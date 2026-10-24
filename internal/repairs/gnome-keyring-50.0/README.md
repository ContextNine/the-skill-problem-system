# GNOME Secret Service missing-client repair

Ubuntu gnome-keyring 50.0-1 can return a failed property lookup without a
`GError` after the PKCS#11 client record disappears. GLib then aborts in
`invoke_get_property_in_idle_cb`, taking the whole Secret Service down and
relocking native consumers. A reboot or automatic restart does not repair it.

The patch returns `G_DBUS_ERROR_FAILED` from that lookup and both OpenSession
negotiators when their existing session lookup fails. It keeps the access
failure, crypto algorithms, keyring format and encrypted custody unchanged.
It creates no identity and reads no installed keyring files.

The included integration test injects a missing client into the real collection
property callback and invokes it through GLib's real D-Bus dispatcher. It uses
an isolated bus and no stored values. The old lookup reproduces the exact
GLib assertion and SIGABRT; the repaired lookup returns a normal D-Bus error.
All 63 upstream tests pass with the patch.

The related [upstream OpenSession repair](https://gitlab.gnome.org/GNOME/gnome-keyring/-/merge_requests/112)
does not cover the property lookup. This local patch is maintained separately.
The original initiating client on the affected machine is not established.

## Build and activate

Use APT's authenticated Ubuntu source metadata to obtain `gnome-keyring=50.0-1`
and its build dependencies. Pass a fresh extracted source directory to:

```sh
bash build.sh /absolute/path/to/gnome-keyring-50.0
```

The script builds the ordinary Debian packages as version `50.0-1+ctx9.1`,
including their test suite. It neither installs packages nor restarts services.
Keep the original source package and produced checksums for review/rebuild.

After checking package metadata and test results, install the reviewed daemon
package through `dpkg -i`. Re-read installed broker status and registered
sessions before restarting `gnome-keyring-daemon.service` once. A restart ends
its native unlocked state. The operator uses the registered hidden terminal
prompt to unlock it, then verifies ordinary installed Notenv execution.
Do not probe live collection properties or launch repeated unlock requests.

Rollback uses the original Ubuntu package. It does not revert encrypted data,
but restores the known crash bug, so preserve evidence before rolling back.
Normal newer distribution packages may supersede this version; verify their
missing-client handling before treating the local repair as retired. No APT
hold or repository-wide update policy is introduced.
