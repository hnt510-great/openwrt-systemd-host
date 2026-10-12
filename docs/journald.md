# Persistent journald on OpenWrt

The native-systemd firmware keeps journal files in `/srv/journal` on the
writable root filesystem. With NVMe extroot mounted by OpenWrt preinit, this
directory is on the NVMe automatically. No separate log partition or
hard-coded NVMe device name is needed. Without extroot, it uses the internal
writable overlay instead; verify extroot before relying on NVMe capacity.

OpenWrt normally links `/var` to `/tmp`. `Storage=persistent` alone would
therefore still put logs in RAM. The `systemd-openwrt` package installs a bind
mount from `/srv/journal` to `/tmp/log/journal`, or `/var/log/journal` when
`CONFIG_TARGET_ROOTFS_PERSIST_VAR=y`. The journal flush service requires this
mount before moving early-boot logs from `/run` to persistent storage. If the
mount fails, flushing fails and journald continues with its runtime journal;
router services can still boot. OpenWrt already selects root/extroot before
systemd starts. This mount does not configure or format extroot.

## Limits and automatic deletion

Defaults in `/etc/systemd/journald.conf.d/openwrt.conf`:

| Setting | Default | Purpose |
| --- | --- | --- |
| `Storage` | `persistent` | Keep logs across reboots |
| `SystemMaxUse` | `1G` | Limit persistent journal usage |
| `SystemKeepFree` | `1G` | Reserve free space for other root/extroot data |
| `SystemMaxFileSize` | `64M` | Rotate persistent files at this size |
| `RuntimeMaxUse` | `128M` | Increased RAM allowance before flush or on failure |
| `RuntimeKeepFree` | `64M` | Reserve free space on `/run` |
| `RuntimeMaxFileSize` | `16M` | Bound individual runtime files |
| `MaxRetentionSec` | `30day` | Remove archived files older than 30 days |
| `MaxFileSec` | `1day` | Rotate files at least daily when logging |
| `Compress` | `yes` | Compress eligible log payloads |

Journald deletes the oldest archived files automatically as limits are
reached. Retention is an upper bound, not a guarantee of 30 days: heavy logging
or low free space can shorten history. Active files are not vacuumed, so
usage is not an exact quota, and the free-space setting cannot reclaim space
used by other applications. `openwrt-journal-rotate.timer` also rotates and
applies journald's configured limits 15 minutes after boot and once daily,
including when little new output is being written.

Edit the drop-in to change these limits, then apply it as root:

```sh
systemctl restart systemd-journald
journalctl --flush
```

Drop-ins are applied in filename order. If using a separate override, name it
after `openwrt.conf`, for example `zz-local.conf`, and inspect the effective
configuration with `systemd-analyze cat-config systemd/journald.conf`.

This configuration is preserved by normal configuration backups/upgrades.
Journal data under `/srv/journal` is deliberately excluded from the usual
configuration backup; rebooting keeps it, but formatting/replacing the
root/extroot or flashing over its filesystem may remove it. Existing devices
with a locally preserved `Storage=volatile` drop-in must merge the new defaults
after upgrading the package. Persistent logging here covers journald output;
OpenWrt router `logread` output remains managed separately by logd.

## Inspect storage and history

Run these commands on the firmware as root:

```sh
findmnt -T /overlay
findmnt -T /srv/journal
findmnt -T /var/log/journal
df -h /srv/journal
systemctl status tmp-log-journal.mount systemd-journal-flush.service
systemctl list-timers openwrt-journal-rotate.timer
systemd-analyze cat-config systemd/journald.conf
journalctl --disk-usage
journalctl --list-boots
journalctl -b -1 --no-pager
```

Use `var-log-journal.mount` instead of `tmp-log-journal.mount` if persistent
`/var` is enabled. Confirm `/overlay` is backed by the intended NVMe partition
and `/var/log/journal` is a mount of the persistent directory. A bind mount
reported as an overlay filesystem is expected: `/srv/journal` is accessed
through OpenWrt's merged root.

## Delete or export logs

Run only the cleanup command matching the history you want to keep:

```sh
# Keep at most 7 days of archived history.
journalctl --rotate --vacuum-time=7d

# Reduce archived history to 256 MiB; active journal files remain additional.
journalctl --rotate --vacuum-size=256M

# Clear all archived history, including logs from before this rotation.
journalctl --rotate --vacuum-size=1
```

Rotation closes current files before vacuuming, so their entries can be
deleted too. Journald keeps newly active files and continues recording new
events: clearing history does not make disk usage zero. Vacuum settings are
one-time cleanup operations; change the drop-in for ongoing retention.
These operations affect the system and user journals in the default namespace,
not logd or files written directly by applications. Avoid deleting open
`.journal` files with `rm` while journald is running.

To export history before cleanup:

```sh
journalctl --since '7 days ago' -o export > /srv/journal-backup.export
```

Move the export off the device if it must survive loss of the NVMe. Export
files are outside journald's retention limits and need separate deletion.

## Validation

The package build and full `make -j2 V=s` image build passed on 2026-10-12.
The signed `systemd-openwrt-3.apk` verified against the firmware's APK keys.
An isolated KVM/UEFI guest cold-booted the rebuilt image, then migrated its
overlay to a separate emulated NVMe namespace using ext4. `/overlay` was
confirmed to mount `/dev/nvme0n1` before systemd started.

Journal markers survived both an internal-overlay reboot and an NVMe-extroot
reboot; migrating the overlay retained earlier history. Journal verification,
rotation and clearing all archived history passed, and new logging continued
after clearing. A temporary 2-second retention override verified that the
rotation service deletes expired history; the shipped 30-day configuration
was then restored. A deliberately invalid mount source prevented flushing,
kept logging in `/run` with the 128 MiB limit, and allowed router services to
boot. Restoring the mount returned logging to persistent storage.

The existing native guest smoke checks passed on NVMe extroot: native units,
ubus/LAN, timers, sockets, cgroup limits, journald and logread. No physical
NVMe was formatted or configured; these results establish VM behavior.
Procd recovery also booted with NVMe extroot, LAN and logread working, then
returned to native mode with the persistent journal active and no failed units.
The disposable VM was powered off after validation.
The `CONFIG_TARGET_ROOTFS_PERSIST_VAR=y` variant is handled by package path
substitution but was not separately boot-tested.

The reproducible persistence/cleanup smoke test is
`scripts/tests/journald-guest-smoke.sh`: run `record` in a disposable guest,
reboot, then run `check`. Its `clear` mode deliberately deletes guest journal
history. Evidence is saved at
`/srv/openwrt-validation/journal-validation-20261012/`.

Tested image:
`bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz`

SHA-256:
`eb87f4bfeafd9af0583c6a4a04ec0f3b28cddfed50f34ed1f46c0d221b2cdee8`
