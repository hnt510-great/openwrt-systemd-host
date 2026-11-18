# Native auxiliary services (`cron`, `nlbwmon`, `ddns-go`), upstream sync and Linux 7.3.5 validation — 2026-11-18

Validated the freshly built native-systemd EFI image (`7.3.5-69-openwrt`, built
via `python3 scripts/build-and-publish.py build-only -j16 V=s`) in a disposable
KVM/UEFI VM (2 vCPUs, 2 GiB RAM, isolated user-mode NICs) using
`scripts/tests/kernel-upgrade/vm-console.py`, including normal native-systemd
boots, an artificial rc delay + in-rc `cron restart` boot, and a `procd`
recovery boot (`openwrt.init=procd`). The physical router was not modified, no
feeds were published, and no Git commits were created.

- Built image: `bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz`
  (SHA256: `9d8095e2c1fed227d1df3be733e0ee39691b7bd33a6d46e4aa9bed85b7d0a8db`,
  kernel `Linux OpenWrt 7.3.5-69-openwrt #0 SMP PREEMPT_DYNAMIC 2026-11-18 05:24:21 +0000 x86_64`)
- Installed packages verified in the VM (`apk list -I`):
  - `busybox-1.38.0-r13`
  - `nlbwmon-2025.06.02~29236be6-r6`
  - `ddns-go-6.17.1-r4`
  - `systemd-openwrt-15`, `systemd-openwrt-services-10`
  - Upstream sync updates: `libmbedtls21-3.6.8-r1`, `odhcpd-ipv6only-2026.11.16~1c662962-r1`,
    `luci-lua-runtime-26.321.72866~cc975fd`, `luci-app-passwall-26.322.13217~16158ae`,
    `libfontenc-1.1.10-r1`, `libXfont2-2.0.10-r1`, `libgtop-2.41.4-r1`

## Findings and fixes during validation

1. **`cron` rc-boot deadlock prevention**: Several OpenWrt rc/hook callers
   (`passwall`, `wgserver`, `alfred`, `librespeed`) invoke `/etc/init.d/cron restart`.
   Because `cron.service` orders `After=openwrt-services.service` (so `sysfixtime`,
   `system` timezone, and rc crontab writers run first), `cron-systemd` checks
   `openwrt-services.service` `ActiveState` and passes `--no-block` while
   `openwrt-services.service` is `activating`, preventing a synchronous deadlock
   while still supporting blocking calls after boot. `cron-systemd reconcile` also
   handles the empty-at-boot `/etc/crontabs` transition without reviving a manually
   stopped service on unrelated `/etc/config/system` edits.
2. **`ddns-go` root-only UCI permissions**: `/etc/config/ddns-go` has mode `0600`
   (`root:root`), which caused `ExecCondition=` running as `User=ddns-go` to fail
   with exit status 1 during the initial VM run. `ddns-go.service` now runs
   `ExecCondition=+/usr/libexec/ddns-go-systemd condition` and
   `ExecStartPre=+/usr/libexec/ddns-go-systemd prepare` as root, writing
   `/run/ddns-go/env` (`0644` inside `RuntimeDirectory=ddns-go`) before `ExecStart`
   drops privileges to `ddns-go:ddns-go`.

## Boot timing and rc-isolation results

| Boot scenario | `systemd-analyze time` | `nlbwmon` ready | `openwrt-services.service` | `dns` / `luci` / `smb` / `ssh` |
| --- | --- | ---: | ---: | --- |
| Clean native boot (`7.3.5-69-openwrt`) | `6.753s` kernel + `22.560s` userspace = `29.314s` (`multi-user.target` `22.554s`) | `23.47s` (`openwrt-services` `activating`) | `26.41s` | `22.98s` / `23.96s` / `24.95s` / `26.66s` |
| Native boot + 12s `S90` rc delay + `/etc/init.d/cron restart` inside rc | `6.901s` kernel + `32.637s` userspace = `39.539s` (`multi-user.target` `32.633s`) | `23.74s` (`openwrt-services` `activating`) | `38.71s` | `23.02s` / `23.85s` / `24.98s` / `38.98s` |

- `nlbwmon.service` and `ddns-go.service` (`135ms` startup) started right after
  `network-online.target` (`23.17s`), in parallel with the remaining `openwrt-services.service`
  rc queue, and were unaffected by the 12-second `S90` rc delay.
- Calling `/etc/init.d/cron restart` synchronously inside `S90` completed without
  blocking or deadlocking `openwrt-services.service`; `cron.service` became active
  immediately after `openwrt-services.service` finished.

## Checks

| Check | Result |
| --- | --- |
| Host auxiliary adapter tests (`scripts/tests/test-auxiliary-systemd.py`) | PASS, 6 cases |
| Service bridge host tests (`scripts/tests/test-systemd-service-bridge.py`) | PASS, 29 cases against staged `root-x86-systemd` |
| Host NAS & Samba adapter tests (`test-nas-systemd.py`, `test-samba4-systemd.py`) | PASS, 8 + 14 cases |
| Mainline kernel & build-input tests (`test-mainline-kernel-updates.py`, `test-kernel-build-inputs.py`, `test-package-metadata-kconfig.py`) | PASS, 20 + 7 + 4 cases |
| `systemd-analyze verify --man=no multi-user.target cron.service cron-config.path nlbwmon.service nlbwmon-config.path ddns-go.service ddns-go-config.path samba4.service wsdd2.service avahi-daemon.service` | PASS, zero warnings/errors |
| Ordering cycles, failed units, pending jobs in VM | None |
| Ownership & cgroup isolation | `cron.service`, `nlbwmon.service` (`Nice=19`), `ddns-go.service` (`Uid != 0`) all `Transient=no` in `/auxiliary.slice` (`CPUWeight=100`); absent from `ubus call service list` and `/openwrt.slice` |
| Remaining 16 `openwrt-*` procd transient units | All 16 (`blockd`, `console@{tty1,ttyS0}`, `dnsmasq`, `haproxy`, `irqbalance`, `log`, `network`, `odhcpd`, `rpcd`, `sysntpd`, `uhttpd`, `urngd`, `uwsgi`, `wpad@{hostapd,supplicant}`) active and healthy |
| `scripts/tests/auxiliary-systemd-guest.py --disposable-vm` | PASS: Linux `7.3.5-69-openwrt`, `/sys/kernel/btf/vmlinux`, `kernelctl check`, bridge exclusion, idempotent start, `nlbw` IPC, `SIGKILL` crash recovery (`cron` `5.212s`, `nlbwmon` `5.104s`, `ddns-go` `5.124s`), `cron-config.path` edit + empty-directory stop/restart, `nlbwmon` `wan6` vs `lan` hotplug, `ddns-go` UCI enable/disable lifecycle |
| `scripts/tests/nas-systemd-guest.py --disposable-vm` | PASS: all 10 NAS lifecycle & discovery checks |
| Upstream sync & Linux 7.3.5 basic router checks | `nslookup localhost 127.0.0.1`, HTTP/HTTPS `192.0.2.1` (`200`), `ubus call luci getVersion`, `ubus call dhcp ipv6leases` (`odhcpd`), `nft list tables` (`table inet fw4`) all PASS |
| `procd` recovery boot (`openwrt.init=procd` via `owrt-rescue-procd`) | PASS: PID 1 `procd`, `cron`, `nlbwmon` (`PID 3913`), `ddns-go` (`PID 5819`), `network`, `dnsmasq`, `odhcpd`, `uhttpd`, `rpcd` active under procd |

Evidence directory: `/srv/openwrt-validation/auxiliary-systemd-validation-20261118/vm-run-1/`
(`native-boot1.json`, `native-delayed-rc.json`, `upstream-health.json`,
`aux-guest-results.json`, `nas-guest-results.json`, `procd-recovery.json`,
`systemd-analyze-verify.txt`, `serial.log`).

## Online procd-to-systemd upgrade migration follow-up — 2026-11-18

Fixed a `PKG_UPGRADE=1` gap where first-time online APK upgrades from `procd`-supervised packages left native units `disabled` after reboot because `post-upgrade` skipped `systemctl enable`. Added `/etc/systemd/openwrt-migrated/<service>` tracking (`cron`, `nlbwmon`, `ddns-go`, `samba4`, `wsdd2`, `avahi-daemon`) so first migration checks `/etc/rc.d/S[0-9][0-9]<service>` and enables the systemd units without starting duplicate processes before reboot, while subsequent upgrades preserve manual `systemctl disable`.

- Host checks after fix: `test-auxiliary-systemd.py` (6/6), `test-nas-systemd.py` (8/8), `test-samba4-systemd.py` (14/14), `test-systemd-service-bridge.py` (29/29) all PASS.
- Disposable KVM/UEFI VM online-upgrade + reboot validation (upgrading `busybox-1.38.0-r14`, `nlbwmon-2025.06.02~29236be6-r7`, `ddns-go-6.17.1-r5`, `samba4-*-4.24.5-r10`, `wsdd2-2023.12.21~b676d8ac-r6`, `avahi-*-0.9_rc5-r5` from a simulated pre-migration state with `/etc/rc.d/S*` present, no `wants/` symlinks, and no migration stamps):
  - Pre-reboot: all 11 units enabled, all 6 migration stamps written, 0 native services prematurely started alongside `procd`.
  - Post-reboot: `systemctl is-system-running` = `running`, 0 failed units, all 11 units `enabled`, all 6 services (`cron`, `nlbwmon`, `ddns-go`, `samba4`, `wsdd2`, `avahi-daemon`) `active`.
  - Subsequent `PKG_UPGRADE=1` after `systemctl disable nlbwmon.service nlbwmon-config.path`: `nlbwmon.service` remained `disabled`.
  - Evidence directory: `/srv/openwrt-validation/auxiliary-systemd-validation-20261118/vm-upgrade-test/` (`vm/serial.log`).
