# OverlayFS warnings: diagnosis and validation, 2026-10-22

The physical router `openwrt` (`192.0.2.1`) was inspected and repaired
without rebooting, flashing, or restarting its running containers. The local
image was rebuilt and tested in a disposable KVM/UEFI VM.

## Diagnosis

The saved kernel journal contained 1,245 historical OverlayFS warnings.
Of these, 1,225 were the same Aria2 rootless layer warning, occurring about
every ten seconds during the affected period:

```text
overlayfs: fs on '/overlay/containers/32771/storage/overlay/l/…' does not support file handles, falling back to xino=off.
```

The underlying NVMe filesystem is ext4. This message does not establish a
filesystem fault: `ovl_can_decode_fh()` first requires
`capable(CAP_DAC_READ_SEARCH)` in the initial user namespace. Rootless
mounts lack that capability, so `xino=auto` falls back to off. The local
kernel enables `CONFIG_OVERLAY_FS_XINO_AUTO=y`.

The separate boot warning about a null UUID in lower filesystem `/` comes
from SquashFS, which has no filesystem UUID. Its root OverlayFS mount also
falls back to `xino=off`. See the
[kernel OverlayFS documentation](https://www.kernel.org/doc/html/latest/filesystems/overlayfs.html)
for the file-handle and UUID requirements.

## Changes

| Package | Installed version | Change |
| --- | --- | --- |
| `openwrt-podman-rootless` | `4` | Generate `nodev,xino=off`; upgrade only the exact old generated config, keeping a backup and preserving customized configs and storage. |
| `podman` | `5.8.4-r7` | Set `xino=off` in temporary rootless capability probes, including probes which ignore storage mount options. |
| `fstools` | `2026.10.18~907cf449-r2` | Select `xino=off` when pivoting over a SquashFS lower root; keep other lower filesystems and the global kernel default unchanged. |

Both remote users, `desktop-user` and `aria2`, now have `mountopt =
"nodev,xino=off"`. Their graphroots remain under `/overlay/containers/UID/storage`.
The Podman feed change is also stored in
`patches/feeds/0019-packages-podman-overlay-xino.patch` for reproduction.
No kernel configuration, ABI, or generation changed:
`6.18.55~628a4581533e057afecd1eb41702012b-r1`, generation `g23`.

## Validation

- Seven config-preservation/migration tests passed, including customized
  configs, symlinks, old populated stores, idempotence, and backup collisions.
- Package builds, full image build, strict Kconfig validation, fstools
  checkpatch without signoff enforcement, Go formatting, and Git whitespace
  checks passed. `.config` and unrelated existing changes were preserved.
- The exact final image cold-booted with no OverlayFS warnings. A fresh
  rootless store on a disposable ext4 disk passed image import, native
  OverlayFS mounts, writes, subordinate-ID ownership changes, five size
  queries, and config migration without any OverlayFS warnings. The ext4
  container directory was bind-mounted under `/overlay/containers`; this
  was not a new extroot failover or migration test.
- All three APKs verified against the router's trusted keys. Offline
  simulation selected exactly those three upgrades, with no kernel or
  kmod changes, before installing the identical artifacts.
- On the physical router, 26 size-list queries over at least a minute and
  a fresh disposable Aria2-image container mount/write/chown test passed.
  There were no new OverlayFS journal entries; the historical count remained
  1,245. Logs were preserved rather than cleared.
- All four existing container IDs, process IDs, and start times remained
  unchanged. Native Overlay Diff remained true for both users; pasta remained
  selected. LuCI, AriaNg, and SearXNG returned HTTP 200, and the router had
  no failed systemd units.
- Boot ID, kernel, firewall/Passwall/network/DHCP configs, subordinate IDs,
  global container configs, normalized nftables structure, and IPv4/IPv6
  proxy exit addresses were unchanged. Four installed executable/library
  hashes matched the tested image.

Image:
`bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz`

SHA256:
`0f95d6e5b7ed3c3223160281b6b94d28e8d0e03ff3df741f3070f45ee4cabec3`

Evidence is in
`/srv/openwrt-validation/overlayfs-repair-20261022T0610/`.
Remote rollback APKs and original configs are in
`/root/overlayfs-repair-20261022T0610/`; each migrated user also has a
`storage.conf.pre-xino` backup.

## Boundaries and remaining warnings

The router's current root mount already operates with `xino=off`. Installing
fstools updates its writable root, but cannot replace the early-boot copy in
the read-only `/rom`. The SquashFS boot-warning fix is embedded and verified
in the new image; activating that early-boot change on the physical router
requires a future image flash. No physical cold boot was performed and no
feeds were published.

The disposable VM's `openwrt-kernel-boot.service` failed with `Existing rescue
GRUB configuration must be inspected`. This limits acceptance to the tested
OverlayFS behavior; it is not full kernel-upgrade or fresh-image acceptance.
The VM was shut down after testing. Offline test-harness mistakes and their
corrected successful runs are retained in the evidence directory.

Other physical-router boot warnings were inventoried but not changed:

| Warning | Assessment |
| --- | --- |
| Old Intel microcode; unsafe late-update warning | N5105 firmware/microcode issue. Kernel logs also report missing mitigations. Needs separate early-microcode/firmware work. |
| `kvm_amd: CPU 0 isn't AMD or Hygon` | AMD driver probe on this Intel system. |
| `it87` and `nct6775` could not be probed | Hardware-monitor drivers did not find supported hardware. |
| HPET missing address/IRQs in `_CRS` | Firmware resource description warning. |
| NVMe `using unchecked data buffer` | NVMe ioctl path warns once when controller SGL validation support is absent; this message is not an ext4 error. |
| Early missing module folders / internal-overlay kmodloader failure | The immutable root lacks the running generation's module directory; the directory is present after the external overlay is mounted. |
| Early missing fstab entries | Seen during preinit before the final storage configuration is available; the live NVMe ext4 overlay mounts successfully. |
| Out-of-tree `button_hotplug` and ENERGY_PERF_BIAS messages | Module taint and boot power-policy notices, separate from OverlayFS. |
