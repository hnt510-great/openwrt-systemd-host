# Extroot recovery upgrade validation — 2026-10-14

**Settings and data preservation passed. Reusing the old extroot did not
produce a clean package migration.** The test used an isolated KVM VM with
the physical router's exact `/etc/config/fstab` and a 4 GiB virtual NVMe.
No physical-router configuration, package, kernel, or boot state was changed.

## Test layout

| Item | VM configuration |
| --- | --- |
| Platform | QEMU/KVM, q35, OVMF UEFI, two CPUs, 3 GiB RAM |
| Firmware disk | Virtual SATA `/dev/sda`, 128 MiB FAT boot partition and 8 GiB firmware/root partition |
| Extroot disk | Separate 4 GiB QEMU NVMe, `/dev/nvme0n1p1`, ext4, label `extroot` |
| Extroot UUID | `00000000-0000-4000-8000-000000000002`, matching the router's setting inside this isolated VM |
| Mount | `/overlay`, `noatime`, enabled |
| Global fstab settings | `delay_root=10`, `check_fs=1`, auto mount/swap enabled, anonymous mount/swap disabled |
| Boot mount entry | UUID `1234-ABCD`, `/boot`, disabled, matching the router |
| Network | QEMU user networking; SSH forwarded only to host `127.0.0.1:22464`; no LAN bridge |

The copied fstab was byte-identical to the router's configuration:
`ab9b82e98b2651a4103b06b6327ca46a06b9d31c2399a0e1cfe0d57ad54183dd`.

The starting image was a private copy of the retained
`podman-validation-20261013/base.img`, revision `r37224+49-0ad1348fb2`.
The target was an unchanged copy of the current built native-systemd
squashfs combined EFI image, revision `r37259+54-2d1c9d1b85`:

```text
bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz
SHA256 3d83851c12409faba5431b6df95d0b5cdf1c468aeeeabfbe7363eef519a249f6
```

Both images use kernel
`6.18.55~ef561c78a2b577ae422f9289311ff293-r1`. This is a real change of
firmware contents, but does not validate a different kernel ABI. The VM
reproduces the storage layout and mount settings, not the router's complete
installed application state or its exact older firmware image.

## Procedure actually tested

1. Booted the older image in native systemd mode. Partitioned and formatted
   only the named 4 GiB emulated NVMe, with explicit serial/size guards.
2. Installed the router's fstab into the internal overlay, copied the overlay
   to the virtual NVMe, then rebooted. Verified NVMe mounted at `/overlay`,
   the exact fstab was active, and no systemd units had failed.
3. Created a UCI configuration marker, unlisted data under `/srv`, a 2 MiB
   random payload with mode `0640`, and an overlay file marker. Saved hashes,
   permissions, machine ID, package inventory, and a stopped-VM checkpoint.
4. Rebooted and selected the actual GRUB `procd recovery` entry. Verified PID 1
   was procd and NVMe extroot was mounted there too.
5. Installed one small signed, script-free `extroot-upgrade-probe` APK into
   the VM's extroot, after an offline simulated transaction selected only
   that package. This deliberately exercised retained package database state.
6. Uploaded the target image directly to recovery `/tmp`. Checked its SHA256,
   complete gzip decompression, and `sysupgrade -T`. Ran ordinary
   configuration-preserving `sysupgrade`, without force/reset flags.
7. Captured the first post-flash boot, rebooted again, and compared the active
   extroot, data/configuration hashes, permissions, identity, services, and
   package metadata with the pre-upgrade state and exact target image.

The serial log proves the upgrader wrote `/dev/sda1` and all **8,589,934,592
bytes** of `/dev/sda2`, unmounted the NVMe, and rebooted. It emitted the
previously observed overlay-remount warning while switching to ramdisk;
the subsequent unmount, full writes, and successful boots were verified.
The SSH connection closed during procd handoff, so completion was assessed
from serial logs and post-boot checks, not the disconnected SSH exit status.

## Observed results

| Check | Result |
| --- | --- |
| GRUB recovery selected; PID 1 procd | Passed |
| Image hash, decompression, `sysupgrade -T` | Passed |
| Actual firmware write and return to native systemd | Passed |
| Fstab restored after flashing | Byte-identical to router configuration |
| First boot after upgrade | Internal F2FS overlay; saved fstab restored after extroot selection |
| Second boot after upgrade | NVMe ext4 mounted at `/overlay` with `noatime` |
| UCI configuration marker | Preserved |
| Unlisted NVMe data and random payload | Hashes unchanged; these data files were not in the sysupgrade backup |
| Payload permissions/ownership | Preserved: `0640`, UID/GID 0, 2,097,152 bytes |
| Machine ID | Preserved |
| Signed test package | Files and installed-package record preserved on extroot |
| New `/rom` firmware and APK database | Match the target image reference |
| Systemd failed units after both post-upgrade boots | Zero |
| procd, dnsmasq, ubus, LuCI HTTPS | Working; HTTPS returned 200 |
| Active APK database after reusing extroot | Still the old database: clean package migration failed |

The second boot's package inventory was exactly the pre-upgrade extroot
inventory. It contained 938 packages, including the probe. The target
firmware database contained 953 packages. Four versions differed:

| Package | Retained extroot metadata | Target firmware metadata |
| --- | --- | --- |
| `base-files` | `1724~0ad1348fb2` | `1724~2d1c9d1b85` |
| `openwrt-desktop` | `9` | `11` |
| `crun` | `1.28-r1` | `1.28-r2` |

Sixteen packages present in the new firmware were absent from the active
old database, including the new Samba/Avahi and RDP dependencies. This is a
metadata discrepancy; absence from the database does not mean the new
firmware's underlying files are absent. Old files in a writable overlay can
also override the new firmware, so retaining the whole old overlay needs
separate migration work.

## Implication for the physical router

The tested keep-settings recovery upgrade preserves the fstab and leaves
the separate NVMe data available. **A second reboot was needed to activate
extroot in this test.** Seeing a small internal overlay immediately after
flashing did not mean the NVMe had been erased.

Storage preservation alone is insufficient to approve a physical firmware
upgrade. A clean upgrade needs a planned migration to a fresh overlay,
selective configuration/data restoration, and installation of packages
matching the new firmware. Do not copy the old APK database or old system
binaries wholesale into that fresh overlay. Such a clean migration was not
performed or validated in this run, and no physical flash is authorized by
this VM test.

See [OpenWrt extroot guidance](https://openwrt.org/docs/guide-user/additional-software/extroot_configuration)
and this tree's [recovery procedure](systemd.md#administration-and-recovery).

## Evidence and cleanup

Evidence is retained at:

```text
/srv/openwrt-validation/extroot-upgrade-validation-20261014-115416/
```

Key files are `results.json`, `before.json`, `recovery-before.json`,
`first-boot-after.json`, `second-boot-after.json`,
`package-metadata-comparison.json`, `new-image-reference.json`,
`upgrade-boot.log`, `serial.log`, `commands.log`, and `vm.py`.

The VM was powered off, its localhost SSH listener closed, and both virtual
disks passed offline `qemu-img check`. The retained boot disk was compacted
to approximately 527 MiB; the 4 GiB virtual NVMe occupies approximately
34 MiB on the host. Before-upgrade checkpoints are retained for review.

The physical router's boot ID, fstab, kernel image, installed package list,
network, firewall, and DHCP hashes were identical before and after testing.
The two unrelated existing host VMs remained running. The main build
configuration and published LAN feeds were not changed.
