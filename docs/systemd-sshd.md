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

`openwrt@sshd.service` is excluded from the default-on service-control bridge;
it reports that the native unit should be used. Native SSH does not register
an instance with procd, even if the init script is called manually.

Kernel adoption and trial-health checks query `sshd.service`. An inactive
native listener fails that health check.

## Init script compatibility adapter

On systemd-only x86/64 images (`CONFIG_OPENWRT_SYSTEMD=y`), OpenSSH installs
`sshd-native.init` as `/etc/init.d/sshd` (`patches/feeds/0046-packages-systemd-only.patch`).
Its `boot`, `shutdown`, and `depends` actions exit 0 so `openwrt-services.service`
never starts a competing daemon, while `start`, `stop`, `restart`, `reload`,
`status`, `running`, `enable`, `disable`, and `enabled` delegate directly to
`systemctl ... sshd.service`. Stock non-systemd builds retain their original
procd init script.

## Images and APK updates

Fresh native images enable `sshd.service` during offline root assembly, without
contacting the build host's systemd. Packages do not ship a managed wants
symlink that would reappear after every upgrade and undo `systemctl disable`.

Native APK hooks reload unit definitions and use `try-restart` to update an
already-active native listener. They preserve inactive/disabled units. Initial
online installation enables the unit for a future boot without starting it.
Service removal stops and disables the native listener.

## Validation

Run from the repository root:

```sh
python3 -B scripts/tests/test-sshd-systemd.py
node scripts/tests/test-sshd-startup-view.js
python3 -B scripts/tests/test-systemd-service-bridge.py
```

Build OpenSSH, `systemd-openwrt`, `systemd-openwrt-services`, LuCI system
settings, and the full native image. Boot the exact image in disposable QEMU
VMs to validate native listener ownership, lifecycle and crash recovery, reload
failure and LuCI rollback, preserved sessions, reboot enablement, signed APK
updates, PAM/logind/SFTP, router services, and native failsafe.
Keep image hashes and VM receipts separate from physical-device evidence.
See the [accepted build and VM validation report](systemd-sshd-validation.md).
