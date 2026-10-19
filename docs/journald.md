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
after upgrading the package. Journald also stores OpenWrt router syslog and
kernel messages; logd reads the journal to provide the legacy interfaces.

## Unified logging and OpenWrt compatibility

In normal systemd boots, journald owns `/dev/log` through
`systemd-journald-dev-log.socket`. It collects syslog (including procd-captured
service output), kernel messages and native systemd service output directly.
`ForwardToSyslog=no` remains intentional: logd reads journal files through
libsystemd rather than receiving forwarded datagrams. Kernel messages are
therefore read once, and a logd restart cannot interrupt journald collection.
Application-only log files and output explicitly discarded by applications or
service configurations require their own configuration; they are not tailed.
Existing journald rate limits still apply, so this does not promise lossless
delivery during overload or storage failures.

Procd still owns `/etc/init.d/log` and starts `logd -J` when PID 1 is systemd
and the native preflight created `/run/openwrt-journald-primary`. The runtime
marker keeps package post-install starts in an older boot on the old logging
path until the next reboot.
This mode does not bind `/dev/log` or read `/proc/kmsg`. The logd account uses
supplementary `systemd-journal` membership to read journal files after dropping
root privileges. Its compatibility view includes only the local system journal
for the current boot, excluding separate user journal files. User records that
journald places in a shared runtime/system journal are part of that view too.
At startup it seeds the
newest records fitting the UCI-configured buffer before exposing the ubus log
object, then follows new entries. Seeding does not replay history to UCI file
or remote forwarding clients. Those clients retain their existing best-effort
delivery behavior; use the journal for retained history.

`logread`, ubus `log.read`, the existing LuCI System Log page, and UCI
`log_file`/`log_ip`/TCP/UDP settings remain available. Native system service
output now also appears in this view. Record timestamps, priorities, facilities
and identifiers come from the journal. Legacy entries remain limited to 1023
bytes, with control characters represented as spaces; the journal retains the
original message. Entries too large for a very small UCI buffer are skipped
by the compatibility reader. As before, local7 debug messages are excluded from the logd
ring. Ubus `log.write` submits once to journald, and the reader observes it
asynchronously. Journal rotation, vacuuming and the runtime-to-persistent flush
are followed without taking ownership of an input socket.
The reader checks the runtime and persistent journal directory identities once
per second. If a bind mount covers a watched directory, it reopens the journal
and resumes after its saved cursor, preserving the compatibility buffer and
avoiding history replay.
Logread also bounds stream-subscription requests and frees the previous pipe
watcher before reconnecting, so existing forwarders can resume after logd
restarts without replaying the journal's startup history.

```sh
readlink /dev/log
# /run/systemd/journal/dev-log
systemctl is-active systemd-journald-dev-log.socket
journalctl -b -t netifd --no-pager
journalctl -b -k --no-pager
journalctl -b --grep='(?i)(error|failed|timeout)' --no-pager
logread -e netifd
```

The systemd package explicitly enables PCRE2 (`libpcre2`) for journalctl's
`--grep` regular-expression filtering.

Router services remain procd-managed, so their trusted systemd unit is generally
`openwrt-procd.service`, rather than a native unit named after each daemon.
Use syslog tags such as `journalctl -t dnsmasq` to filter them.

### Upgrade and recovery

Install matching journal-capable logd and systemd-openwrt packages together.
Do not switch ownership of `/dev/log` on a running installation. Apply the
transition on the next boot after reviewing preserved configuration. Older
images installed `/etc/systemd/system/systemd-journald-dev-log.socket` as a
symlink to `/dev/null`; remove that legacy package mask before the next native
boot. Preserve other administrator socket overrides. An incomplete migration
(legacy mask or logd without `-J` support) fails the native preflight and falls
back to procd recovery with a diagnostic.

Recovery/failsafe and non-systemd builds keep stock logd ownership of `/dev/log`
and `/proc/kmsg`, without opening the journal. Existing UCI logging and firmware
recovery controls remain available there. Journald does not collect new recovery
boot logs. No upgrade hook restarts logging services or reboots the machine.

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
not the independent logd compatibility buffer or files written directly by
applications. Avoid deleting open
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

## Unified logging checks

On the build host:

```sh
python3 scripts/tests/test-logd-journal.py
make -j4 package/system/ubox/compile package/system/systemd/compile package/system/systemd-openwrt/compile V=s
```

The host tests exercise the actual C record converter, directory identity
changes, forwarder request failures/timeouts and pipe cleanup, plus boot-mode
selection. They need downloaded ubox sources and staged development headers.

Run the following as root only in a disposable VM using the rebuilt firmware:

```sh
python3 logd-journal-guest.py --disposable --vacuum
sh systemd-guest-smoke.sh
sh journald-guest-smoke.sh record
# Reboot, then:
sh journald-guest-smoke.sh check
```

The unified smoke test checks PCRE2, metadata, binary/long messages, a 256-record
batch, separate user-journal isolation, restart catch-up, rotation/vacuum,
file/UDP/TCP forwarding, forwarder recovery after killing logd, and a 1 KiB
compatibility buffer. `--vacuum` deliberately deletes archived VM history.

To check failed persistent mounting and recovery of the existing reader:

```sh
python3 logd-journal-guest.py --disposable --prepare-storage-failure
# Reboot this disposable VM, then:
python3 logd-journal-guest.py --disposable --storage-recovery
```

This creates an explicitly named test drop-in, then removes only that drop-in
when recovering the mount and flushing to persistent storage. Recovery verifies
that subsequent messages arrive and pre-flush history is not replayed.
After booting the GRUB procd recovery entry, use
`python3 logd-journal-guest.py --disposable --recovery` to test the stock path.

## Unified logging validation (2026-10-19)

Built logd/ubox `2025.10.30~6f78fa49-r8`, systemd-openwrt `8`, and
systemd/libsystemd `262-r4`. PCRE2 was enabled explicitly and tested with
non-capturing groups and case-insensitive journal searches. The affected
package builds and full `make -j4 V=s` firmware build passed. Signed APKs
verified against the local build public key.

Three host tests passed, including actual C converter, mount identity and
forwarder lifecycle regression fixtures and four boot-selection combinations.
Strict `conf --fatalrecursive`, shell syntax, patch style and diff checks
passed. Existing LuCI journal backend tests (seven cases) and JavaScript view
tests passed. The non-systemd logd/logread branch also cross-compiled; its
`-J` rejection was checked without opening a logging input. Build metadata
still emitted existing missing bmx7 feed dependency warnings; these were
separate from the successful strict Kconfig check.

The exact rebuilt EFI image passed fresh KVM boot, the unified logging suite,
native router/timer/socket/cgroup smoke checks, prior-boot journal retention
and journal verification, and the GRUB procd recovery logging/LAN checks.
Guest executable hashes matched the built root filesystem. Tests covered
priority/facility/time/PID mapping, binary and long messages, 256-record
batching, separate user journals, catch-up, rotation/vacuum, file/UDP/TCP
forwarding after observed connection readiness and logd respawn, and a 1 KiB
compatibility ring.

An additional isolated VM verified signed package upgrade without changing
the running logd PID or `/dev/log` ownership before reboot, fallback to procd
with the legacy mask retained, and journal persistence on emulated NVMe
extroot. It also passed deliberately failed persistent mounting followed by
runtime logging, live mount/flush recovery, and continued ingestion without
history replay. These results cover VMs; physical-router deployment and the
`CONFIG_TARGET_ROOTFS_PERSIST_VAR=y` boot variant were not tested. Existing
unrelated tracked diffs and the exact `.config` bytes were preserved.

Tested image:
`bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz`

SHA-256:
`e386e7ce96777507941822093bcb6c6c07b74d782bf2b1f9025528d6b6cc4175`

Evidence: `/srv/openwrt-validation/logd-journal-validation-20261019/`, including
`final-image.json`, `accepted-payload-hashes.json`, `commands.jsonl`, host/build
logs and the VM serial logs.
