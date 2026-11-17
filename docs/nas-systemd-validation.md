# Native NAS discovery (`wsdd2` and `avahi-daemon`) validation — 2026-11-17

Validated the combined native-systemd NAS group (`samba4` + `wsdd2` + `avahi-daemon`
in `nas.slice`) in a disposable KVM/UEFI VM (2 vCPUs, 2 GiB RAM, isolated user-mode
NICs) using `scripts/tests/kernel-upgrade/vm-console.py` against the existing
base image upgraded with signed APKs. **No procd recovery boot was tested in the VM.**
The physical router was not modified, no feeds were published, and no Git commits
were created.

- Base image: `bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz`
  (SHA256: `1e5d196950554321c9498187258407f8c10c981df3e6dc9f2f582cf8b844a399`)
- Signed APKs installed offline (`apk --repositories-file /dev/null add --no-network`):
  - `systemd-openwrt-services-9.apk` (`3c045df16eb07a6958c7322eeda8b4e6d807aeba10b9a5f2dc7e74b5df4b61e1`)
  - `wsdd2-2023.12.21~b676d8ac-r5.apk` (`73d69d768cd3e29346b079b5afa94110ae350a2226d9dfb2b6d49d017b57cc98`)
  - `avahi-dbus-daemon-0.9_rc5-r4.apk` (`e8326001c6cb6f53c9d99e99e23418690b195203f5a6416786110c784e95eabe`)
  - `avahi-utils-0.9_rc5-r4.apk` (`c0fde98ef441aac9e91da6b78643099e3fa17ed9a0928f31ed8d2162dce3a394`)
  - `libavahi-client-0.9_rc5-r4.apk` (`54ed6373df9041f967acf22af4a151583c2c545d6d2cd502b86cd520d9255eff`)
  - `libavahi-dbus-support-0.9_rc5-r4.apk` (`8c5d5a3543ae9a8291ec4a762c96fc11df8dc8ddccdc4d40b75364e0b9367245`)
  - `samba4-server-4.24.5-r9.apk` (`88152d9b62f5f679cef20704f145f29f0857f877913eb08ce1e3d76d1811dcf6`) and matching `samba4-{libs,client,utils}-4.24.5-r9.apk`

## Boot timing and race comparison

| Boot scenario | `systemd-analyze time` | `openwrt-services.service` | `avahi-daemon` ready | `samba4` / `wsdd2` started |
| --- | --- | ---: | ---: | --- |
| Baseline (`procd` transient `samba4`, `wsdd2`, `avahi-daemon`) | `6.727s` kernel + `27.320s` userspace = `34.048s` | `21.199s` (finished at `31.075s`) | `25.57s` (`_smb._tcp` observed) | `smb` `26.75s` / `wsdd2` `31.21s` (`sleep 5`) |
| Native NAS (`samba4` + `wsdd2` + `avahi-daemon` in `nas.slice`) | `6.794s` kernel + `19.920s` userspace = `26.714s` | `16.068s` (finished at `26.036s`) | `23.075s` D-Bus (`32ms` start) / `23.935s` mDNS | `smbd` `23.575s` / `wsdd2` `23.630s` |
| Native NAS + 12s artificial `S90` rc delay | `6.852s` kernel + `31.730s` userspace = `38.582s` | `27.797s` (finished at `37.829s`) | `23.148s` D-Bus / `25.296s` mDNS | `smbd` `23.629s` / `wsdd2` `23.679s` |

Removing `wsdd2`'s `sleep 5` from the `procd` rc queue reduced `openwrt-services.service`
by `5.13s` and overall `multi-user.target` userspace time by `7.40s`, while `wsdd2`
started `7.58s` earlier (`23.630s` vs `31.21s`). With an artificial 12s rc delay,
all three NAS units still started at ~23.1–23.7s without waiting for `openwrt-services.service`.
At ~24.6–24.9s, `br-lan` IPv6 DAD (`ifupdate`) triggered `samba4-reconfigure.service`,
which atomically updated `/var/etc/smb.conf` and cleanly cascaded through `wsdd2-config.path`
to restart `wsdd2.service` with zero errors or failed units.

## Checks

| Check | Result |
| --- | --- |
| Host NAS adapter tests (`scripts/tests/test-nas-systemd.py`) | PASS, 8 cases |
| Host Samba adapter tests (`scripts/tests/test-samba4-systemd.py`) | PASS, 14 cases |
| Service bridge host tests (`scripts/tests/test-systemd-service-bridge.py`) | PASS, 29 cases |
| Signed APK upgrade before reboot | PASS; `PKG_UPGRADE=1` left 0 active native NAS units alongside live `procd` |
| `systemd-analyze verify --man=no multi-user.target samba4.service samba4@smbd.service wsdd2.service avahi-daemon.service` | PASS, zero warnings/errors |
| Ordering cycles, failed units, pending jobs in VM | None |
| Ownership & cgroup isolation | `samba4@{smbd,nmbd}`, `wsdd2`, `avahi-daemon` all `Transient=no` in `/nas.slice`; absent from `ubus call service list` and `/openwrt.slice` |
| Remaining 17 `openwrt-*@*.service` procd transient units | All 17 (`blockd`, `cron`, `ddns-go`, `dnsmasq`, `haproxy`, `irqbalance`, `log`, `network`, `nlbwmon`, `odhcpd`, `rpcd`, `sysntpd`, `uhttpd`, `urngd`, `uwsgi`, `wpad@{hostapd,supplicant}`) active and identical to baseline |
| `scripts/tests/nas-systemd-guest.py --disposable-vm` | PASS: idempotent start, bridge exclusion, `samba4` stop/start cascade to `wsdd2`, `SIGKILL` crash recovery (`wsdd2` 5.214s, `avahi-daemon` 5.226s + `_smb._tcp` republish 2.128s), `SIGHUP` reload, `samba4` UCI `workgroup` cascade to `wsdd2`, `lan` vs `wan6` hotplug, inactive reload stays stopped |
| `scripts/tests/samba4-systemd-guest.py --disposable-vm` | PASS: all 10 Samba lifecycle & SMB I/O checks |

Evidence directory: `/srv/openwrt-validation/nas-systemd-validation-20261117/vm-run-1/`
(`baseline-procd.json`, `native-boot1.json`, `native-delayed-rc.json`, `after-online-upgrade.json`,
`nas-guest-results.json`, `samba-guest-results.json`, `systemd-analyze-verify.txt`, `serial.log`).
