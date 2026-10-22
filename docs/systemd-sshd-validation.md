# Native OpenSSH validation — 2026-10-22

The native OpenSSH migration passed package builds, a complete firmware build,
host tests, signed APK migration tests, and disposable QEMU boot/runtime tests.
The five validated userspace APKs were subsequently published and installed on
the physical router using the guarded live handover recorded below.

## Accepted image and packages

Image:

```
/srv/openwrt-validation/openwrt-sshd-systemd-validation-20261022/images/openwrt-x86-64-generic-squashfs-combined-efi.img.gz
```

SHA-256:

```
00231f97c82ea9a018395dfcfbb0a6aaeb43ce64cbdfb69de024962b6ed3ab6f
```

Build command, with the user's `.config` preserved:

```sh
make -j4 V=s CONFIG_PACKAGE_systemd-openwrt-services=m \
  BIN_DIR=/srv/openwrt-validation/openwrt-sshd-systemd-validation-20261022/images
```

The optional bridge remains absent from the fresh image, matching the existing
configuration; its signed package was installed separately in the VM.

| Package | Validated version |
| --- | --- |
| openssh-server-pam | 10.6_p1-r3 |
| systemd-openwrt | 10 |
| systemd-openwrt-services | 3, optional |
| luci-mod-system | 26.284.81002~524c586-r2 |
| openwrt-kernel-upgrade | 1-r17 |

The kernel support package update is required because its adoption/trial health
check previously called `/etc/init.d/sshd status`. It now checks the installed
native unit, with the original fallback for older installations.

## Results

Host checks passed:

- SSH integration scripts: 16 tests.
- Service bridge binary/IPC: 23 tests.
- Kernel upgrade helpers: 52 tests, including native SSH health selection and
  failure without a fallback to a second supervisor.
- Node Startup view tests, shell/JavaScript syntax checks, strict Kconfig
  validation with the bridge disabled/enabled, and systemd unit verification.
- Bridge C checkpatch: zero errors and warnings. All three Git diffs passed
  whitespace checks.

The exact image booted through a fresh disposable qcow2 overlay with q35/KVM,
UEFI, two vCPUs, 2 GiB RAM, and restricted LAN/WAN user networks. Nine installed
runtime payload hashes matched final image/package staging, including the
stripped optional bridge binary.

| Runtime scenario | Result |
| --- | --- |
| Fresh boot | Native listener ready; no SSH instance registered with procd |
| Kernel adoption | Completed naturally on first boot with native SSH health |
| Native lifecycle | Start, stop, restart, completed reload and crash recovery passed |
| Invalid configuration | Reload left the listener alive; startup refused to open a listener |
| LuCI rollback | A deliberately failing native reload restored the configuration file |
| Stopped service | LuCI save validated configuration without starting SSH |
| Existing connections | The controlling SSH session survived listener stop/restart/crash |
| Authentication | Root/ordinary-user password and public-key login, incorrect-password rejection, and PAM/logind SSH sessions passed |
| SFTP | A throttled 1 MiB transfer survived listener restart and matched its original hash |
| Host keys | Preserved across preparation, lifecycle tests and reboots; invalid keys were not replaced |
| Optional bridge | Installation passed; legacy SSH controls were rejected in favor of sshd.service |
| Normal reboot with SSH disabled | Native SSH remained inactive; recovery rc.d setting remained enabled |
| Procd recovery | Original SSH supervision, reload and LuCI backend passed |
| Failsafe | Original temporary-key SSH helper accepted a real connection; systemd was absent |
| Return to normal boot | Enabled native SSH, bridge, router services and kernel checks passed |
| Native regressions | Existing timer/socket/cgroup/logging smoke script passed |
| Router checks | LAN DNS, firewall, journal/logread compatibility and service health passed |

The failsafe VM received a transient LAN address matching the isolated harness;
its default failsafe address and firmware configuration were not changed.
Failsafe retained the original early init process; it did not run systemd.

Browser inspection confirmed that Startup displays the native-service notice
and omits SSH init-script controls, while the SSH Access page renders the
existing configuration. Helper reload/rollback behavior was tested in the VM.

## APK migration and enablement

A separate disposable VM booted the previous image with procd-owned OpenSSH.
Trusted signatures and the exact five-package offline simulation passed before
installation. The transaction retained the existing listener PID, configuration
and host-key hashes; it did not automatically activate the native unit.
After explicit native enablement and reboot, the native runtime suite passed.

An additional signed offline repository test reinstalled the native OpenSSH
package while its unit was disabled but active. The package refreshed the
listener, preserved disabled enablement, and retained the controlling session.
Offline installation and masked-unit preservation also passed host tests.

## Signed publication and physical live handover

On 2026-10-22, an isolated source root containing exactly the five accepted APKs
was published to the LAN ABI feed. The dry run reported no same-version
replacements. All five HTTP downloads matched the frozen SHA-256 values, and
the independent kernel channel's index hash, image map and generation sequence
were unchanged. The router successfully refreshed its signed repository indexes.

A disposable VM first exercised the live transition and its automatic rollback.
The timer downgraded all five packages to their previous signed versions and
restored the procd listener. A second live upgrade matched the physical router's
five-package transaction, including the bridge upgrade from version 2 to 3.
An established SSH session survived the ownership transfer and native restart;
a new connection also succeeded.

The physical router at `192.0.2.1` verified both package sets, simulated exactly
five upgrades offline, and retained protected backups before installation.
Independent transient systemd services performed activation and armed a
ten-minute rollback timer. After package installation and configuration
validation, activation restarted only the optional service bridge, deleted only
procd's `sshd` registration, waited for the old listener to exit, and enabled
and started `sshd.service`. Procd and networking were not restarted.

Acceptance at `2026-10-22 03:27:47 UTC` confirmed:

- `sshd.service` enabled and active, listener PID 30373 in
  `/system.slice/sshd.service`, listening on IPv4/IPv6 port 22.
- No procd SSH instance; the LuCI helper reports `systemd`.
- Fresh SSH and SFTP connections, successful native restart and reload, and
  survival of the connection established before installation.
- Unchanged SSH configuration and host keys, accounts, network/firewall/Passwall
  configuration, recovery rc.d links, boot ID and running kernel.
- Unchanged nftables rules after normalizing dynamic set elements; DNS answers,
  active router/procd/bridge services, and the LuCI HTTPS login form. LuCI's
  unauthenticated response remains HTTP 403, as before deployment.

The rollback timer was cancelled only after these checks; it did not execute
on the physical router. The previous signed APKs, protected backup and activation
logs remain in `/root/sshd-native-deploy-20261022` on the router. Publication,
live VM rollback, package transactions and acceptance receipts are retained in
the validation directory's `deployment/` subdirectory. No reboot, image flash,
kernel installation, commit or push occurred.

## Kernel and validation boundaries

Kernel source and configuration were not changed. The exact release/ABI remains
`6.18.55-owrt-628a4581533e057afecd1eb41702012b-r1-g23`; configuration extracted
from the previous image's kernel metadata matches the current kernel build.
The complete build regenerated the kernel binary, so binary identity with the
previous firmware is **not** claimed:

- Previous image kernel SHA-256:
  `144aedfc4c64eb416501f6320a5956d4a79a9ac6ce2c7587b0de569be601dfc8`
- Accepted image kernel SHA-256:
  `4cb1112582669f17c1909373a872269865e053608bbf975e86d42c3b4586e70b`

No kernel APK publication or physical kernel upgrade was performed.
Physical NICs, PPPoE, watchdog behavior and firmware flashing were not tested.
A DHCP probe received a lease from QEMU slirp (`192.0.2.2`), so that probe is
excluded from evidence for the router's own DHCP server.

## Evidence and preservation

Receipts, frozen signed APKs, the accepted image, serial logs and VM overlays
are retained under:

```
/srv/openwrt-validation/openwrt-sshd-systemd-validation-20261022/
```

`release/phase-results.json`, `release/payload-verification.json`,
`migration-final/upgrade.log`, `kernel-identity.json` and `preservation.json`
identify the accepted results. Earlier development images/logs are separate.
The source configuration, main/packages/LuCI HEADs, stashes and staged changes
were preserved. Unrelated main-tree changes were unchanged. No commits or
pushes were made. Test VMs were shut down after validation.
