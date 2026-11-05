# systemd supervision validation (2026-11-04)

Validation of [systemd supervision of OpenWrt services](systemd-native-supervision.md):
procd 2026.11.01~0d3c5dc1-r6 with `130-systemd-transient-units.patch`,
systemd-openwrt 14, systemd-openwrt-services 5 and hardware-support 3.

Scope: host tests and disposable KVM/UEFI virtual machines only. No physical
device was flashed or upgraded, nothing was published, and the router was not
contacted.

Validated image (built with `scripts/build-and-publish.py build-only -j12`,
kernel publication sequence 49 reused):
`bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz`

SHA-256:
`7eb491a82447f4a0cda9e5bf54808d284ff9eb19994147cce5f3a82ba367b90c`

## Host checks

| Check | Result |
| --- | --- |
| `scripts/checkpatch.pl --no-tree --no-signoff` on patch 130 | 0 errors, 0 warnings |
| procd clean prepare and compile from the package patches | passed, no fuzz |
| `python3 -B scripts/tests/test-procd-units.py` | 8 tests passed |
| `python3 -B scripts/tests/test-systemd-service-bridge.py` | 24 tests passed, including the new unit placement case |
| `git diff --check` | clean |

## Guest checks

One router VM (2 CPUs, 2 GiB, fresh overlay, personal WAN integrations
disabled as in `scripts/test-image-network.py`) ran
`scripts/tests/procd-units-guest.sh` and `scripts/tests/systemd-guest-smoke.sh`.
The console reached a shell 47.5 s after QEMU started.

| Check | Result |
| --- | --- |
| `openwrt-procd.service` runs `procd --systemd=units` | passed |
| `ubus call system watchdog` reports owner systemd; `{"stop": true}` rejected | passed |
| Instances reported with `systemd_unit` | 20: 15 active (dnsmasq, netifd, odhcpd, rpcd, uhttpd, logd, sysntpd, cron, blockd, avahi, haproxy, irqbalance, nlbwmon, urngd, uwsgi), samba4 ×2 in auto-restart, 3 exited |
| procd children other than hotplug helpers | none |
| Probe service: `Restart=always`, `RestartUSec=1s`, `StartLimitBurst=4`, `LimitNOFILE=1024`/`512` soft, slice, environment, stdout in the journal, `service list` pid | passed |
| `reload` with unchanged configuration keeps the process | passed |
| `config.change` trigger on an instance with `reload_signal` sends SIGHUP, same PID | passed |
| `kill -9` of the main process: systemd restart, `respawn_count` ≥ 1 | passed |
| Configuration change without `reload_signal` replaces the unit (new PID and environment) | passed |
| Stop removes the unit and the procd instance | passed |
| `respawn 3600 0 2` with `exit 3`: crash loop logged after the start limit, `exit_code` 3 | passed |
| `udevadm trigger --action=change` on `/sys/class/mem/null` runs `/etc/hotplug.d/mem` once, `DEVNAME=null` | passed |
| `systemctl restart openwrt-procd`: rc sequence reruns, dnsmasq returns with a new PID, coldplug not repeated | passed |
| Existing native smoke test (PID 1, bridge units, timer, socket activation, cgroup limits, journal and logread) | passed |
| `systemctl --failed`; `is-system-running`; procd fallback warnings | none; `running`; none |

Observed in the VM: `samba4` crash-looped. This was first attributed to a
missing account in the fresh overlay; the router showed the real cause (see
below). `ttyd` exits because `/etc/uhttpd.crt` has not been generated yet on a
fresh overlay. Both are reported through the units path (auto-restart and exit
status). `sysstat` and `urandom_seed` are one-shot instances that completed.

## Router and client network test

`python3 scripts/test-image-network.py --image <the image above>` booted a
router and a LAN client VM: status `passed` with native-init, router-services,
wan-dhcp, lan-dhcp, dns, routing-nat, luci-auth, luci-http and ubus-board all
true.

## Router deployment (2026-11-04)

The packages were published after a passing preflight and installed on the
router with `apk upgrade` (10 packages, world unchanged, no restarts). After the
administrator rebooted it:

| Check | Result |
| --- | --- |
| PID 1 systemd; `openwrt-procd` runs `--systemd=units`; `is-system-running` | `running`, no failed units; 11.0 s kernel + 30.8 s userspace |
| Router daemons as units | 19 active (dnsmasq, network, odhcpd, rpcd, uhttpd, logd, sysntpd, cron, miniupnpd, nlbwmon, ddns-go, daed, ttyd, uwsgi, haproxy, avahi, blockd, irqbalance, urngd) |
| PPPoE WAN, DNS, ping, WireGuard handshake, `fw4` table, LuCI login page | working |
| GNOME session, logind seat, udev rules for audio/input/video | present |
| `/dev/kvm`, render node | 0660, set by `libvirt-openwrt-prepare` as before |
| samba4 | **failed**: `smbd`/`nmbd` exit with `Failed to create session` and hit the start limit |

The Samba failure is the `setsid()` conflict described in the guide. Fixed in
samba4 4.24.5-r5 (feed patch 0030); the fix was booted in a VM (no restarts,
ports 139/445 listening, all 14 guest checks passing; image SHA-256
`9912dc3ae83d3dc23666f4853b90f6792df2cac3bf8ce95c43a4bbc4b8f29881`), published,
installed on the router, and a share listing on 192.0.2.1 returned `desktop-user`
and `downloads`. File reads and writes from a client were not tested.

Also observed on the router: miniupnpd exits once at boot because its STUN
lookup precedes DNS, then runs after restart. nginx is enabled but not running.
A same-version rebuild of `daed-2.1.1-r4.apk` differed from the published bytes;
the publisher refused it and the published file was restored.

## Not covered

- No x86/64 watchdog driver is selected (`ITCO_WDT`, `SP5100_TCO` and
  `I6300ESB_WDT` are unset), so the guest had no `/dev/watchdog`; systemd's
  `RuntimeWatchdogUSec=30s` was confirmed, a watchdog reset was not exercised.
- The GRUB procd recovery entry, failsafe and a recovery flash were not booted
  again. Units mode is only entered with `--systemd=units`; the shared changes
  on the procd-PID-1 path are the static ujail timeout buffer and the
  `instance_running()` wrapper.
- Button events (`button-hotplug`) and physical block, network and USB hotplug
  were not exercised; the udev forwarding path was tested with a synthetic
  change event.
- The rollback drop-ins were not booted.
- GNOME desktop, Sunshine and libvirt guest suites were not rerun in a VM
  (the router's desktop session was only observed to be present).

Evidence: `/srv/openwrt-validation/procd-units-validation-20261104/` (`image.img.gz`,
`final-guest/` serial logs, `router.commands.log` and `results.json`,
`network/validation.json`; `vm1`–`vm4` and `debug1` hold the earlier runs on
the first image, including the two test-expectation fixes).

## External instance control guard (2026-11-05)

Scope: source/package checks and a fresh disposable KVM/q35 UEFI VM booted from
`openwrt-x86-64-generic-squashfs-combined-efi.img.gz`. The final VM used the
image unchanged, with no replacement bridge binary. It ran systemd `262-r12`,
`systemd-openwrt-services-6` and kernel `7.3.1-51-openwrt`. The build-only
wrapper reused generation 51 because kernel inputs were unchanged.

Image SHA256: `903f651a5f1f3cfea84114048de5190f907140198ff6f97583591337dcc58e9e`.

| Check | Result |
| --- | --- |
| Both package builds and `build-and-publish.py build-only -j12 V=s` | passed; no publication |
| Quilt patches 001/002 against the original systemd 262 tarball | zero fuzz; patched files identical to prepared source |
| Bridge host suite; procd packaging suite | 25 tests passed; 9 tests passed |
| Strict `conf --fatalrecursive`, shell syntax, `git diff --check` including the new patch | passed |
| Direct start/stop/restart/reload, try-restart and reload-or-* on unitprobe | exit 4 with init-script advice; MainPID and NRestarts unchanged; procd still reports running |
| D-Bus Manager.StopUnit, Unit.Stop and EnqueueUnitJobMany | refused; mixed batch leaves the bridge PID unchanged |
| D-Bus marked jobs and varlink EnqueueMarkedJobs | refused before changing other marked units; varlink returns the advice in its optional message field |
| CanStart/CanStop and RefuseManualStart/Stop | no/no and no/no respectively; requester PID/comm refusal lines found in the journal |
| Init-script restart, stop, start; direct start after collection | owner operations succeed; direct start returns exit 4 with the not-running message |
| `systemctl restart netifd` | hint names `openwrt@network`; original command still fails |
| `systemctl kill -s KILL`, crash loop, UCI reload triggers, udev forwarding | passed; respawn counted; slice stop remains allowed |
| `systemctl restart openwrt-procd` | instances recreated with a new PID; stop phase timed out and required SIGKILL (see below) |
| Native smoke including explicit stop of file-backed openwrt-smoke@ instances | passed; timer/socket activation, cgroup limits and both log paths work |
| Final VM state | running; zero failed units |

The restart assertion proves instance recreation, **not a clean procd stop**.
The final procd journal records a `stop-sigterm` timeout, SIGKILL and inherited
scope-placement connection timeouts before successful restart. This lifecycle
observation is retained as a limitation; no procd or cgroup-layout source change
was made in this feature.

A separate disposable boot of the pre-feature 2026-11-04 image reproduced the
same stop timeout and inherited scope-placement warnings, followed by `running`
and zero failed units. That baseline ran systemd `262-r11`, procd
`2026.11.01~0d3c5dc1-r6` and kernel `7.3.1-49-openwrt`; its image SHA256 is
`7eb491a82447f4a0cda9e5bf54808d284ff9eb19994147cce5f3a82ba367b90c`. The comparison is recorded in
`baseline-restart/{results.json,lifecycle.log,router.commands.log}` under the
same evidence directory. Thus the stop-timeout limitation predates this guard;
it was not repaired or treated as a clean restart by this feature.

The additional `test-apk-source-versions.py` run has two existing next-release
simulation errors: nginx-ssl-util `1.7-r8` and native-libs-dev `1-r7` are reserved
migration identities. Their current recipes were not changed by this feature;
this is separate from the passing feature suites and full image build.

No feed publication, router installation/reboot, live daemon-reexec, recovery
boot, physical client network acceptance, or GNOME/Sunshine/libvirt guest-suite
rerun is claimed.

Evidence outside the repository:
`/srv/openwrt-validation/systemd-external-control-validation-20261105/`:
`image.img.gz`, `full-build-verified.log`, `patch-apply.log`, `patch-check.json`,
`bridge-tests-final.log`, `procd-tests-final.log`, `kconfig.log`,
`apk-source-versions.log` and `guest-184725/` (results, command log, serial log,
feature outputs and journal). Earlier guest directories are diagnostic attempts,
including the bridge crash-loop health failure subsequently fixed.
