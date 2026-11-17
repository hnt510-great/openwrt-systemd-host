# Native Samba validation — 2026-11-17

Validated the normal native-systemd boot in a disposable KVM/UEFI VM with
2 vCPUs, 2 GiB RAM and isolated user-mode NICs. Both the procd baseline and
native Samba tests used systemd as PID 1. **No procd recovery boot was tested.**
The physical router's SMB was not contacted, installed, restarted or rebooted;
no feed publication or Git commit/push was performed.

The VM used the existing base image plus signed userspace package upgrades,
not a newly rebuilt firmware image:

- Base: `bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz`.
  SHA256: `1e5d196950554321c9498187258407f8c10c981df3e6dc9f2f582cf8b844a399`.
- Final server: `bin/systemd/packages/x86_64/packages/samba4-server-4.24.5-r9.apk`.
  SHA256: `88152d9b62f5f679cef20704f145f29f0857f877913eb08ce1e3d76d1811dcf6`.
  Matching libs, client and utils were also upgraded to r9.
- Bridge: `bin/systemd/packages/x86_64/base/systemd-openwrt-services-8.apk`.
  SHA256: `a55dd1195c01d4231adec4d1ab22f9067ffbfe0459f561f5ff0877c883ae8d81`.

## Findings and repairs

The original r7 units passed the complete dependency check and started, but
waited for the entire `openwrt-services.service` rc queue. SMB became available
at 31.96 seconds rather than the procd baseline's 26.45 seconds. Samba now
waits for the existing `network-online.target` provider instead, allowing it to
start while unrelated rc scripts are still executing.

The original hotplug hook also reloaded LAN-only Samba when WAN6 came up.
The hook now checks Samba's selected UCI interfaces (`lan` by default).

Rapid configuration changes exposed a second rate limit: the generic
reconfigure service could hit its start limit and leave its path watcher
failed. That service now has `StartLimitIntervalSec=0`; explicit configuration
reconciliation resets the daemon start budget before restarting instances.
Automatic crash recovery retains the daemon's 5-starts-per-60-seconds limit.
The final VM suite exercised seven rapid selected-interface updates without
resetting the reconfigure service or path watcher between updates.

## Results

Times below are first observed successful TCP connections from an early-boot
observer to the VM's LAN address, in seconds since kernel boot. They are
individual VM observations, not a statistical speed comparison or a physical
router latency guarantee.

| Normal systemd boot scenario | DNS | LuCI | SMB | procd rc queue complete |
| --- | ---: | ---: | ---: | ---: |
| Original Samba via procd, r6 baseline | 22.66 | 24.23 | 26.45 | 31.74 |
| Final r9, full VM power-off then cold start | 21.87 | 22.48 | 22.84 | 30.03 |
| Final r9, reboot with an unrelated 12-second rc delay | 21.89 | 22.45 | 22.81 | 42.06 |

The deliberate delay ran from 24.69 to 36.70 seconds. In both final boots,
Samba was already accepting connections while `openwrt-services.service` was
still `activating`. The delay fixture was removed before shutting down the VM.

| Check | Result |
| --- | --- |
| Host Samba adapter tests | PASS, 14 cases |
| Service bridge host tests | PASS, 28 cases including native Samba exclusion |
| Final package build, shell/Python syntax and whitespace checks | PASS |
| Signed APK extraction and final-source payload comparison | PASS, all 10 integration files; the installed VM files also match the signed r9 payloads |
| `systemd-analyze verify --man=no multi-user.target samba4.service samba4@smbd.service` in VM | PASS, including the complete actual boot graph |
| Runtime ordering cycles, pending jobs and failed units after final boots | None |
| Ownership | `Transient=no`, `/nas.slice/samba4@smbd.service`, CPUWeight=100; no procd Samba registration or legacy Samba transient units |
| Coexistence | network, dnsmasq, odhcpd, uhttpd, rpcd, wsdd2 and avahi remained active under procd; actual DNS lookup and HTTP responses passed during lifecycle checks |
| Native start and stop | PASS; idempotent start, group stop removes smbd/nmbd; manual start to listening port took 0.193 seconds in the signed-package suite |
| Crash restart | PASS; new PID and listening port after 5.212 seconds |
| UCI path watcher and SMB I/O | PASS; created a disposable guest share, downloaded and uploaded files and compared bytes |
| NetBIOS option | PASS; disabling it stopped nmbd while SMB remained available; restoring the fixture restored the original configuration |
| Invalid template | PASS; rejected without replacing the previous generated configuration or restarting the serving daemon |
| Interface events | PASS; selected LAN event reconciles; unselected WAN6 event preserves PID |
| Rapid reconfiguration | PASS, seven updates with watcher still active and SMB available |
| Inactive reload | PASS; does not start Samba |
| NetBIOS and global IPv6 | NetBIOS lookup passed; TCP 445 accepted connections on the LAN's global-scope IPv6 address |

## Boundaries and remaining observations

The early native start sees IPv6 address availability changes: the cold-boot
log contains two `Cannot assign requested address` bind messages, followed by
a selected-LAN reconfiguration and successful daemon restart at about 24 seconds.
IPv4 was already available at 22.84 seconds. Do not interpret the first TCP
connection as all addresses being ready simultaneously.

IPv6 **link-local** TCP 445 did not accept connections. Repeating the original
procd init path under the same normal systemd PID 1, with the same Samba binary
and configuration, produced the same result; global-scope IPv6 and IPv4 worked
under both paths. This observation is not claimed fixed by the migration.

Recovery/failsafe, AD-DC, physical NICs, PPPoE, Windows/macOS clients, throughput,
loaded-network latency and physical-router deployment remain outside this run.
The base image also logs existing `lm-sensors` and `done` rc-script warnings;
these did not leave failed systemd units and were present outside the migration.

Evidence: `/srv/openwrt-validation/samba4-native-validation-20261117/vm-native-1/`.
`validation.json` records the final passing scope; `inputs.json`,
`r9-inputs/sha256sums.json`, `r9-payload-check.json`,
`runtime-payload-check.json`, the boot/timing snapshots,
`lifecycle-r9-signed.json`, `coexistence-r9-coldboot.json`,
`old-init-normal-mode-comparison.json`, `delayed-rc-details.log` and console/SSH
logs provide the receipts. The reusable target test is
`scripts/tests/samba4-systemd-guest.py --disposable-vm`; it changes Samba state
and must only run in an explicitly disposable test VM.
