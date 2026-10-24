# Linux 7.3 publication and installation, 2026-10-24

Published generation 30 and installed its signed kernel, matching kmods, and
native development headers on router `192.0.2.1`. The user reserved the reboot
for themselves. No reboot, firmware flash, service restart, or VM restart was
performed by this operation. Physical boot acceptance remains pending.

## Published release

The installed candidate is
`7.3-owrt-5001c59b1072ebdf1a2ed551a854f37a-r1-g30`, with ABI
`7.3~5001c59b1072ebdf1a2ed551a854f37a-r1`.

The coordinated publisher passed both a dry run and formal staged preflight
against the actual router, including installed-module coverage and upgrade
simulation against the target ABI's userspace view. It published the matching
7.3 userspace feed view and the signed
[kernel channel](http://192.0.2.164:8088/kernel-upgrades/packages.adb).
The channel retains generations 25 and 30 and contains 1,033 packages.

The published kernel snapshot is
`/srv/openwrt-feeds/public/kernel-snapshots/1792822732292074944`.
Its index SHA256 is
`3622363e150c457f7160bc1a8378fbd185bce31960282f8fcb4bb76b41698edf`;
its manifest SHA256 is
`7211d245893a6a50e2215a8bdc5d51a0583a9b1352839deca5d34744f1de944c`.
Every incoming kernel-channel APK matched the VM-validated build's hash.

## Signed offline installation

The exact published snapshot was copied to a private root-only router directory.
All package hashes and the index hash matched the pinned published manifest;
the router's existing trust verified the signed index and all 1,033 APKs.

The offline simulation used an empty repositories file, the staged signed index,
and `--no-network`. It passed with 511 kernel-related operations and no package
removals or unrelated userspace updates. The world file, package database,
kernel state, and protected constraints remained unchanged by simulation.

Immediately before installation, the transaction inputs were checked again and
the repeated plan matched the reviewed plan. The identical offline transaction
then completed successfully. Final installed versions matched every reviewed
operation, including all 253 logical kmods and their generation-30 payloads,
the kernel image, rolling tracker, and matching development headers.

The existing retention service subsequently removed the retired generation-23
payloads and their 253 checksum anchors from world. Its service exited
successfully. No other world entries were added or removed; unrelated package
versions and user package selections were preserved.

## Verified state before reboot

- Running kernel: `6.18.55-owrt-99d816e22a3cf14cc4aad935e110f3ea-r1-g25`.
- Boot ID remained `00000000-0000-4000-8000-000000000003`.
- Pending candidate: the generation-30 release above; `kernelctl check` passes.
- Known-good remains generation 25; original rescue remains `legacy-6.18.55`.
- GRUB `saved_entry` remains the confirmed generation 25; `next_entry` selects
  generation 30 for a one-time trial.
- All 70 protected configuration/rescue-file hashes were unchanged. SSH, ubus,
  procd bridge services, D-Bus, and journald retained their active states and PIDs.
- Loaded modules were unchanged. The running `ubuntu26.04` libvirt domain retained
  its UUID, running state, and XML hash.
- LAN, WAN, WireGuard, IPv4/IPv6 default routes, persistent NVMe overlay, KVM,
  DNS/firewall/SSH health, and router HTTP access passed final checks.
- `/boot` retained approximately 68 MiB free; the persistent overlay had 77 GiB free.

The user's next reboot will attempt generation 30. Normal continuous health
checks must pass before the manager promotes it to known-good. The saved
generation-25 fallback and original rescue remain available. The earlier
[VM validation](mainline-kernel-validation.md) does not establish that the new
kernel has booted successfully on this physical hardware.

## Backups and evidence

The router's root-only pre-install backup is
`/root/mainline-kernel-backup-20261024T061612Z/state.tar`.
The verified signed snapshot, reviewed plan, and installation plan are retained
under `/root/mainline-kernel-stage-20261024T061612Z/`.

Private host evidence is under
`/srv/openwrt-validation/openwrt-mainline-20261024-084724/deploy-20261024T061612Z/`.
It includes publication receipts, the offline plan and install log, signature
results, package/world comparisons, protected-runtime snapshots,
`final-verification.json`, and `final-health.json`.
