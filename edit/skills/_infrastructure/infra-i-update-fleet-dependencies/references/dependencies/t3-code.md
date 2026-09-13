## T3 Code

Dependency ID: `t3-code`. It uses nightly releases. One fleet operation resolves one exact version, then aligns selected installed CLI/server or macOS desktop artifacts to that version through [[infra-i-update-fleet-coding-tools]].

macOS desktop replacement requires the documented bundle ID, Team ID, signature, checksum, staged backup, and post-install verification in [[native-artifact-updates]]. Linux CLI/server updates preserve service-manager provenance and restart only confirmed managed services. Authentication and task history are never copied. Roll back to the staged verified artifact; removal is separate.
