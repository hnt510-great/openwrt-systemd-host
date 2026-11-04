# Physical installation, 2026-10-15

Installed and enabled the kernel-upgrade mechanism on the physical router
`192.0.2.1` through the existing `openwrt` SSH alias and passwordless sudo.
No firmware was flashed, no kernel was installed or replaced, and the router
was not rebooted. This support-only installation does not require a reboot.
An actual future kernel upgrade requires the user to reboot to run its candidate.

## Defaults and installation

`OPENWRT_KERNEL_UPGRADE` now defaults to `y` under its existing native-systemd,
squashfs and kernel-source constraints. The working `.config` and maintained
`configs/x86-64-systemd-desktop.config` explicitly enable the feature and its
manager/GRUB environment editor. Their next publication sequence is 4, avoiding
reuse of the already published validation generation 3.

The signed, simulated eight-package support transaction completed successfully:

| Package | Installed version |
| --- | --- |
| apk-mbedtls | 3.0.5-r7 |
| ubox | 2025.10.30~6f78fa49-r3 |
| systemd-openwrt | 6 |
| grub2, grub2-efi, grub2-editenv | 2.12-r4 |
| lan-apk-feeds | 2 |
| openwrt-kernel-upgrade | 1-r12 |

The router's existing signing trust verified these packages; no untrusted
installation or ABI override was used. Temporary checksum world constraints
introduced by installing local APK files were removed only for these eight
support packages, allowing normal signed future updates. Existing unrelated
world constraints were preserved.

After loading the original matching `configs` module, `kernelctl migrate`
snapshotted the original modules, firmware and autoload rules, preserved the
original GRUB configuration, and installed the protected GRUB dispatcher and
runtime modules. It did not reinstall GRUB's core. The new boot service is
enabled; systemd received only a daemon reload, with no service restart.

## Preserved physical state

- The boot ID is unchanged; the running kernel remains `6.18.55` and its installed
  exact ABI remains `6.18.55~f10b60a7da5b97b579b974213f7b729c-r1`.
- `/boot/vmlinuz` SHA-256 before/after:
  `bb59edc8c9f6a9673809194d23b5756a286277c85f7c85e7043414418a010d56`.
- All captured original module, UCI configuration and libvirt file hashes match.
- Native systemd, procd/ubus/router services, DNS, SSH and nftables checks pass;
  systemd reports no failed units.
- LAN `192.0.2.1`, WireGuard, WAN/WAN6 and both default routes remain healthy.
- The persistent ext4 extroot remains `/dev/nvme0n1p1`; no repartitioning occurred.
- KVM API and creation of a temporary empty VM pass; libvirt remains accessible.
- `kernelctl check` passes; state is `ready`, known-good is `legacy-6.18.55`,
  pending is null, and GRUB has only `saved_entry=owrt-rescue` with no trial armed.
- The original systemd, procd recovery and failsafe choices remain available.

A root-only backup of the original kernel, GRUB configuration, APK world/database
and configuration archive is at `/root/kernel-feature-backup-20261015/` on the
router. The manager also retains its own protected legacy generation.

## Feed readiness and upgrade boundary

Published the previously QEMU-validated, signed generation-3 channel at
`http://192.0.2.164:8088/kernel-upgrades/packages.adb` (509 packages). Published
its matching ABI-specific feed view before any candidate can be booted. That
view retains current published userspace APKs and replaces ABI-dependent
trackers with the validated matching set. The original ABI feed is unchanged.
Immutable payloads belong to the separate kernel channel and are excluded from
the ABI-specific publisher's input view.

`apk update` and ordinary `apk upgrade --simulate` succeed on the physical router.
The simulation resolves the rolling image, all 248 matching module payloads and
prepared headers: 501 kernel-related operations plus five existing unrelated
userspace updates. Those 506 operations were **not executed**. No new candidate
is staged, so rebooting immediately would still boot the original kernel.

The available candidate is
`6.18.55-owrt-3099baa9ab7a5ed3ea226a586fba0edc-r1-g3`. Its ABI test configuration
differs by disabling printk timestamps, as described in the QEMU validation
report. APK calls the global ABI tracker change a downgrade because of hash
sorting; publication sequence and generation payloads advance together.
Physical candidate boot/promotion/fallback remain untested until an actual
upgrade and user-controlled reboot. The earlier EFI/BIOS QEMU tests cover those
paths, but do not constitute physical hardware boot acceptance.

For a later actual upgrade, simulate and review the transaction, execute it,
then check before rebooting deliberately:

```
sudo apk update
sudo apk upgrade --simulate
sudo apk upgrade
sudo kernelctl check
sudo grub-editenv /boot/grub/grubenv list
```

GRUB retains the confirmed old default during a candidate's one-shot trial.
If a candidate hangs, reset the machine; the following boot returns to the old
saved default. The original kernel can also be selected manually in the menu.

## Evidence and source validation

Evidence directory on the build host:
`/srv/openwrt-validation/kernel-upgrade-validation-20261015/physical-feature-20261015/`.
It contains support simulation/install logs, migration log, protected baseline
hashes, final verification JSON, signed feed publication reports and the actual
upgrade simulation. Baseline metadata is kept private.

Kconfig output written to separate scratch files confirms both explicit
enablement and default enablement with manager/editor selection. Pre-existing
WeeChat recursive dependency diagnostics still occur; this
is not a clean repository-wide Kconfig check. Signed feed dry runs, live APK
signature checks and `git diff --check` pass. No firmware/kernel rebuild was
needed for this configuration-default and support deployment follow-up.

## Subsequent physical G7 acceptance, 2026-10-16

After the user performed the upgrade and reboot, a read-only check confirmed
the running release was
`6.18.55-owrt-f10b60a7da5b97b579b974213f7b729c-r1-g7`. The boot service completed
its continuous 120-second health confirmation successfully. G7 was `known_good`,
`pending` was null, and `previous_good`/`rescue` remained `legacy-6.18.55`.
GRUB's saved default pointed to G7 with an empty `next_entry`.

All 248 logical kmods had installed G7 payloads. All 357 module files had the
running release in their vermagic, and all 249 module metadata records matched
the running release and exact ABI. `kernelctl check` passed for retained and new
kernel files. The original `/boot/vmlinuz` still had the SHA-256 recorded above.

Native systemd reported `running` with no failed units. LAN, WAN, WireGuard,
the active dynamic IPv6 interface, IPv4/IPv6 default routes and the persistent
NVMe overlay matched the captured health baseline. KVM API version 12 and
creation of a temporary empty VM passed, and libvirt queries succeeded. This
check did not start a guest OS or force a physical failed-boot/manual fallback.
The original kernel and protected modules remain available for fallback.

Evidence is in
`/srv/openwrt-validation/kernel-upgrade-validation-20261015/physical-g7-verification-20261016/verification.json`.
The check performed no installation, configuration change or reboot.
