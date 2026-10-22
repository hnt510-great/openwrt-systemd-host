# Native OpenSSH supervision

With `CONFIG_OPENWRT_SYSTEMD=y`, the OpenSSH server package installs a native
`sshd.service`. Systemd supervises the foreground listener, handles crash
restarts, and waits for OpenSSH's startup/reload notifications. Procd retains
all other existing router-service responsibilities.

## Administration

Use the native unit for normal-boot lifecycle and enablement:

```sh
systemctl status sshd.service
systemctl restart sshd.service
systemctl reload sshd.service
systemctl enable sshd.service
systemctl disable sshd.service
journalctl -u sshd.service
```

Plain enable/disable changes future boots without starting/stopping the
listener. Use `--now` when both changes are intended. Stop/restart affects the
listener; established SSH sessions and transfers survive. Shutdown still
terminates sessions through the normal system/session shutdown path.

The service starts after the OpenWrt rc sequence and systemd-user-sessions,
so first-boot configuration and PAM preparation precede login. Its preparation
helper recreates the volatile privilege-separation directory and generates
missing RSA/Ed25519 host keys. Existing keys are validated and never replaced
automatically. Invalid configuration fails validation before startup or reload.

LuCI's OpenSSH page keeps its existing configuration format and authentication
safeguards. It validates the complete configuration, reloads an active native
listener, and restores the previous file on reload failure. Saving while the
native listener is inactive or failed does not start it. LuCI's Startup page
identifies SSH as systemd-managed and omits its procd action buttons.

`openwrt@sshd.service` is excluded from the optional service-control bridge;
it reports that the native unit should be used. Native SSH does not register
an instance with procd, even if the init script is called manually.

Kernel adoption and trial-health checks query `sshd.service` when its native
unit is installed, and retain the init-script check on older procd-owned
installations. An inactive native listener fails that health check.

## Recovery remains independent

The original `/etc/init.d/sshd` implementation and failsafe helper remain
installed. With procd as PID 1, SSH uses the original supervisor and controls.
In systemd mode the init script rejects runtime actions. Its
`enable`, `disable`, and `enabled` commands address **recovery rc.d settings**
only; they do not change native enablement. For example:

```sh
/etc/init.d/sshd enabled   # Recovery-boot setting
systemctl is-enabled sshd # Normal-boot setting
```

Disabling the native unit leaves recovery access enabled if it was enabled
beforehand. Native rcS skips SSH in both its boot and shutdown queues, avoiding
competing supervisors or stops. Stock non-systemd builds retain their original
packaging and lifecycle.

## Images and APK updates

Fresh native images enable the unit during offline root assembly, without
contacting the build host's systemd. Normal and recovery boot settings are
separate. Packages do not ship a managed wants symlink that would reappear
after every upgrade and undo `systemctl disable`.

Native APK hooks reload unit definitions and use `try-restart` to update an
already-active native listener. They preserve inactive/disabled units. Initial
online installation enables the unit for a future boot without starting it.
An online upgrade from the former procd implementation does not transfer its
running listener or start a competing native listener.

For that one-time migration, first install the matching OpenSSH,
systemd-openwrt, openwrt-kernel-upgrade, optional service-bridge, and LuCI
packages together. Explicitly
enable `sshd.service`, then activate the new ownership on the next planned
reboot. A disposable VM must verify the exact package set and boot path before
any physical deployment. Service removal stops/disables the native listener;
recovery package operations continue using the original procd path.

A guarded live handover is also validated: an independent systemd activation
service removes only procd's SSH registration, waits for its listener to exit,
then enables and starts the native unit. Prepare and test an independent rollback
timer with the previous signed packages first; cancel it only after fresh SSH
and SFTP connections and protected-state checks pass. Do not restart procd or
run the handover solely inside the SSH connection being replaced. See the
[publication and physical handover receipt](systemd-sshd-validation.md#signed-publication-and-physical-live-handover).

## Validation

Run from the repository root:

```sh
python3 -B scripts/tests/test-sshd-systemd.py
node scripts/tests/test-sshd-startup-view.js
python3 -B scripts/tests/test-systemd-service-bridge.py
```

Build OpenSSH, systemd-openwrt, the optional bridge, LuCI system settings, and
the full native image. Boot the exact image in disposable QEMU VMs. Validate
native listener ownership, lifecycle and crash recovery, reload failure and
LuCI rollback, preserved sessions, independent reboot enablement, signed APK
updates, PAM/logind/SFTP, router services, procd recovery, and failsafe.
Keep image hashes and VM receipts separate from physical-device evidence.
See the [accepted build and VM validation report](systemd-sshd-validation.md).
