---
type: agent-reference
status: enabled
---

## Worker Mac power and sleep

This is the single authoritative Amphetamine and closed-display procedure for worker Macs.

Set the ordinary unattended baseline first:

```bash
sudo pmset -a sleep 0
sudo pmset -a womp 1 autorestart 1
pmset -g custom
```

`pmset sleep 0` does not override clamshell or maintenance sleep. Install current Amphetamine from the Mac App Store, enable Launch at Login, configure a session that starts at app launch for **Indefinitely**, and disable **Allow system to sleep when display is closed**.

Apple-silicon Mac laptops additionally require Amphetamine's official [Power Protect](https://github.com/x74353/Amphetamine-Power-Protect) package for reliable Closed-Display Mode across power-source changes. Its signed installer places `powerProtect.scpt` in the user's Amphetamine application-scripts container and a restricted sudoers rule for Amphetamine's `pmset -a disablesleep 1|0` commands. The official [Amphetamine Power Protect instructions](https://github.com/x74353/Amphetamine/blob/main/README.md) also require the `Enable Power Protect Install` preference; the files and package receipt alone are not proof that Amphetamine will invoke them. Stop at the installer password or Touch ID prompt and hand it to the user.

Use this exact order:

1. Confirm the supported Amphetamine version, Apple-silicon architecture, AC power, and absence/presence of the documented Power Protect files or package receipt.
2. Install Power Protect through its notarized installer.
3. Verify `defaults read com.if.Amphetamine 'Enable Power Protect Install'` reports `1`. If it is absent or false after the official install, run `defaults write com.if.Amphetamine 'Enable Power Protect Install' -bool TRUE` as the logged-in worker user before restarting Amphetamine.
4. End the current Amphetamine session.
5. Quit and reopen Amphetamine.
6. Start a fresh **Indefinitely** session with closed-display system sleep disabled.
7. Verify Amphetamine recognizes Power Protect and the effective system state blocks closed-display sleep. While the fresh session is active, `pmset -g` must report `SleepDisabled 1`; Amphetamine should also own its user-idle assertions. A different `caffeinate`, Screen Sharing, or unrelated `PreventSystemSleep` assertion is not proof.
8. Remove any temporary submitted `caffeinate` service only after native evidence exists.
9. Disconnect Screen Sharing, wait beyond the former failure window, confirm no new sleep event in `pmset -g log`, and open a brand-new inbound `MACHINE_ID-mesh` SSH connection.
10. Restart once with windows reopening, repeat the idle window and fresh inbound test, and confirm Amphetamine restarted its indefinite Closed-Display session with the Power Protect preference still enabled.

Do not create a persistent `caffeinate`, custom LaunchAgent, or other sleep service automatically. If native Amphetamine/Power Protect still fails, stop, present the evidence, and obtain explicit user approval before any custom fallback.

### Approved fallback

Only after that explicit approval, use the managed controller rather than hand-writing a service:

```bash
sleep_service="$(vault root)/_system/agents/skills/_infrastructure/infra-i-onboard-machine/scripts/manage_worker_mac_sleep_service.py"
registry="$(vault root)/_system/agents/_package/instance/fleet/machines.json"
python3 "$sleep_service" MACHINE_ID --registry "$registry"
python3 "$sleep_service" MACHINE_ID --registry "$registry" --apply
python3 "$sleep_service" MACHINE_ID --registry "$registry" --verify
```

It owns only `~/Library/LaunchAgents/com.ctx9.worker.prevent-system-sleep.plist`, runs `/usr/bin/caffeinate -s` as the logged-in worker user, starts at login, and restarts if it exits. It refuses a different existing plist at that path. `--remove` unloads and deletes only the matching managed plist.

After apply, require all four controller checks: matching plist, loaded LaunchAgent, running exact command, and a `PreventSystemSleep` assertion owned by `caffeinate`. Restart once, rerun `--verify`, disconnect Screen Sharing, wait beyond the former failure window, and prove a brand-new inbound `MACHINE_ID-mesh` SSH connection.

Interpret the power log precisely. A closed display may still produce `Entering DarkWake state due to 'Clamshell Sleep'` display-state lines while `PreventSystemSleep` remains asserted; those lines alone are not a failed gate. Require `pmset -g log` to report no actual system sleep/wake cycle during the window, confirm the selected VPN extension did not suspend for system sleep, and require fresh inbound reachability. Keep the failed native Amphetamine evidence in the private machine note; the fallback does not make native Power Protect successful.
