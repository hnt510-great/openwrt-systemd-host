# Plan: systemd takes over procd's runtime work in native boot

Status: implemented 2026-11-04; see docs/systemd-native-supervision.md and its validation record.

## Context

The user asked whether procd can be removed so that systemd takes over. Today in native boot,
`openwrt-procd.service` runs `procd --systemd`, which still does five jobs:

1. **Process supervision.** It fork/execs every `procd.sh` instance: 38 of the 58 init scripts in the
   image. It also handles respawn, limits, user, ujail, stdout logging and stop timeouts. Patch
   120 only *places* each process in a systemd scope.
2. **Kernel hotplug.** It listens on uevent netlink, runs the `/etc/hotplug.json` and
   `hotplug.json.d/*` rules (makedev/chgrp, `hotplug-call`, `/etc/rc.button/*`), and runs coldplug
   through `udevtrigger`. systemd-udevd also runs (GNOME pulled in `systemd-udev`), so two daemons
   consume every uevent. Their device modes already conflict: procd sets kvm to 0660, udev sets
   it to 0666.
3. **Hardware watchdog.** systemd's watchdog is disabled in `system.conf`.
4. **ubus API.** It provides `service` (set/list/delete/signal/event/validate/get_data/set_data/
   state/watchdog), `system` (board/info/reboot/signal/watchdog/sysupgrade) and `hotplug.<subsys>`.
5. **Early boot** (`/sbin/init` preinit and overlay), failsafe, the GRUB "procd recovery" entry
   and the only firmware-flash path.

The process can't simply be deleted: the ubus API in item 4 is a contract used by every
`procd.sh` script, by LuCI Save & Apply (`reload_config` sends `service event config.change`,
and 23 scripts register reload triggers), by rpcd/LuCI `service list`, and by netifd,
sysntpd (`hotplug.ntp`), dnsmasq dhcp-script and acme.

**Decisions made with the user:**
- Scope: native boot only. procd stays in the image for preinit, failsafe, recovery and flashing.
- Approach: turn procd into a thin ubus frontend. Every instance becomes a transient systemd
  `.service`. udevd owns uevents and devices, and systemd owns the watchdog. procd keeps only the
  ubus API, triggers, validation, the data store and the hotplug.d script runner.

Outcome: in native boot, no router daemon is a child of procd. `systemctl status`, journald,
cgroup limits, restart and stop all belong to systemd. UCI, LuCI, `/etc/init.d/*` and
`service list` keep working unchanged. Recovery and stock builds behave exactly as they do today.

## Ownership after the change (native boot)

| Function | Today | After |
| --- | --- | --- |
| exec, respawn, limits, user, logging, stop | procd (+scope) | systemd transient service |
| uevents, /dev perms, coldplug | procd + udevd (both) | udevd only |
| `/etc/hotplug.d/*`, `/etc/rc.button/*` | procd (from netlink) | procd rule engine, fed by udev forwarder |
| watchdog | procd | systemd `RuntimeWatchdogSec` |
| ubus `service` / `system` / `hotplug.*` | procd | procd (frontend) |
| preinit, failsafe, recovery, flashing | procd | procd (unchanged) |

## Implementation

### 1. procd units mode — new `package/system/procd/patches/130-systemd-transient-units.patch`

All code is under `#ifdef OPENWRT_SYSTEMD` and runtime-gated, so stock builds and recovery boots
keep the existing fork/exec path.

- **Option.** Add `--systemd=units` next to the existing `--systemd`. Keep the old mode as
  `--systemd` (legacy) for one release as a rollback path.
- **Bus connection.** Use one persistent async sd-bus connection to `/run/systemd/private`, driven
  from uloop (`sd_bus_get_fd`/`get_events`/`get_timeout` → `uloop_fd` + `uloop_timeout`), plus
  `Manager.Subscribe` and per-unit `PropertiesChanged` matches. Reuse the property and connection
  helpers in `systemd-cgroup.c` (added by patch 120: `prop()`, private-bus connect, slice-name
  escaping).
- **Starting an instance.** `service/instance.c` `instance_start()` calls
  `StartTransientUnit("openwrt-<svc>@<inst>.service", "fail", props)` instead of fork/exec when
  units mode is on. Name escaping matches the existing `openwrt-<svc>.slice` rules. Property
  mapping:

  | procd param | Unit property |
  | --- | --- |
  | command (+ ujail argv from `jail_run()` when jailed, including capabilities/seccomp) | `ExecStart` (Type=exec) |
  | env | `Environment` (+ procd's PATH) |
  | user / group | `User` / `Group` |
  | limits / nice / no_new_privs | `Limit*` / `Nice` / `NoNewPrivileges` |
  | stdout / stderr / facility | `StandardOutput/Error=journal` or `null`, `SyslogIdentifier`, `SyslogFacility` |
  | term_timeout | `TimeoutStopSec`, `KillMode=mixed` (SIGTERM to the main process, like procd) |
  | respawn threshold/timeout/retry | `Restart=always`, `RestartSec`, `StartLimitBurst=retry+1`, `StartLimitIntervalSec=threshold` (retry 0 → no limit) |
  | respawn_on_failure / respawn_policy | `Restart=on-failure`, `RestartSteps` + `RestartMaxDelaySec` (systemd 262 supports both) |
  | always | `Slice=openwrt-<svc>.slice`, `BindsTo=`+`After=openwrt-procd.service`, `AddRef=yes`, `Description` |

  `Delegate=yes` is set only for jailed instances. ujail's delegated-cgroup lookup
  (`jail/cgroups.c`, patch 120) must then accept its own transient service as the boundary
  instead of creating a scope.
- **Lifecycle.**
  - stop/delete → `StopUnit`
  - restart after a config change (netdev/file/data/command diff, existing
    `instance_config_changed()`) → stop, wait for inactive, `Unref`, start anew
  - `reload_signal` and `service signal` → `KillUnit(main, sig)`
  - when `MainPID` changes, write the pidfile
- **Tracking state.**
  - From unit properties, keep `running`, `pid`, `exit_code` (ExecMainCode/Status) and the
    restart count (NRestarts).
  - Emit the existing ubus events `instance.respawn` when NRestarts increases, and `instance.fail`
    when Result is `start-limit-hit`.
  - One-shot tasks (no respawn, e.g. urandom_seed and sysstat) stay loaded through `AddRef` until
    procd reads their exit status.
  - `instance_dump()` adds `systemd_unit` and keeps the existing fields, so rpcd, LuCI and the
    bridge get the same `service list` shape.
- **Unchanged.** Triggers, validation, `get_data`/`set_data`, mdns, `watch` and the `system` and
  `hotplug.*` objects.
- **Fallback.** Instances that use `vrf`, `trace` or console/stdio fd passing keep the existing
  fork+scope path and log a journal warning. In the current image, `vrf` is only conditional (in
  dnsmasq and uhttpd), and uxc is not selected.
- **Startup.** In units mode, skip `watchdog_init()`, the netlink `hotplug()` listener and
  `procd_coldplug()`. Send READY after ubus registration and the coldplug replay (step 2).
- Bump `PKG_RELEASE` in `package/system/procd/Makefile`.

### 2. Hotplug moves to udevd

- **Feeding procd's rule engine.** In units mode, procd's `plug/hotplug.c` rule engine and its
  serial queue are fed through a new root-only ubus method (`procd.hotplug uevent {env}`) instead
  of netlink. `makedev` and `rm` become no-ops because udev creates `/dev` nodes. `exec`,
  `button` (SEEN computation) and `hotplug-call` keep their current semantics and serialization.
  Their children run in procd's cgroup, so FUSE and other long-lived helpers are not killed by udev.
- **Forwarder.** Add a small C forwarder, `openwrt-udev-forward`, built in the procd tree and
  installed at `/usr/libexec/`.
  - It normalizes `DEVNAME`, because udev's `/dev/sda1` must become the kernel's `sda1`.
  - It exits 0 quietly if procd's object is absent.
  - `package/system/systemd-openwrt/files/90-openwrt-hotplug.rules` runs it only when it is
    needed: `TEST=="/etc/hotplug.d/$env{SUBSYSTEM}"`, `SUBSYSTEM=="button"`, or the v4l-id rule.
- **Coldplug.** systemd-udev-trigger runs in sysinit, before procd exists. After procd registers,
  it replays once per boot (marker in `/run`) with
  `udevadm trigger --action=add --settle --subsystem-match=<hotplug.d kernel subsystems>,button`.
  It does not replay again on a procd restart, so a running GNOME session does not see duplicate
  drm or input add events.
- **Device permissions.** Translate each `hotplug.json.d` file into a udev rule numbered after
  `50-udev-default.rules`, shipped by the package that owns the JSON:
  - `package/system/hardware-support`: audio, audio-capture, midi, video, render, input, kvm 0660,
    lp, v4l-id
  - `package/custom/openwrt-flatpak` and `openwrt-appimage`: fuse 0666
  - `package/custom/sunshine`: uinput 0600

  Network-renaming, firmware and module-loading udev rules stay excluded, so interface names and
  kmodloader behavior do not change.
- **Dependency.** `systemd-openwrt` depends on `+systemd-udev`, because udev becomes mandatory in
  native mode.
- Patch 110 (the libudev-zero rebroadcast) only matters for the netlink path, so it stays for
  stock and recovery.

### 3. Watchdog moves to systemd

- **Config.** In `package/system/systemd-openwrt/files/system.conf`, set `RuntimeWatchdogSec=30s`
  (procd's default timeout) and `RebootWatchdogSec=10min`.
- **ubus.** `system watchdog` in units mode reports systemd's `RuntimeWatchdogUSec`. It rejects
  `stop`/`magicclose` with NOT_SUPPORTED; flashing is already rejected in native mode.
- **Rollback.** The legacy-mode rollback drop-in must also set `RuntimeWatchdogSec=0`, so that
  procd and systemd never both open `/dev/watchdog`.

### 4. `package/system/systemd-openwrt` wiring (PKG_RELEASE 13 → 14)

- `openwrt-procd.service`:
  - `ExecStart=/sbin/procd --systemd=units -S`
  - `After=systemd-udevd.service`, `Wants=systemd-udev-trigger.service`
  - keep `KillMode=control-group` for hotplug children
- `openwrt-services.service`: add `After=systemd-udev-trigger.service`.
- Ship `90-openwrt-hotplug.rules`.
- Document the rollback drop-in, `/etc/systemd/system/openwrt-procd.service.d/legacy.conf`
  (legacy ExecStart plus the watchdog-off setting), in the docs rather than shipping it.

### 5. `package/system/systemd-openwrt-services` bridge

- Read `systemd_unit` from procd instance data in `src/service-bridge.c`, and show unit state
  next to procd state.
- Update the `openwrt*.scope` listing in docs and tests to cover `openwrt-*@*.service`.
- Bump `PKG_RELEASE`.

### 6. Docs (guide + validation pair, English)

- New `docs/systemd-native-supervision.md` covering:
  - the ownership table and unit naming (`systemctl status 'openwrt-dnsmasq@*'`)
  - respawn mapping and its differences from procd: StartLimit uses a sliding window rather
    than consecutive short runs, and `KillMode=mixed` applies
  - the hotplug path and the rollback drop-in
- New `docs/systemd-native-supervision-validation.md`.
- Update `docs/systemd.md`, `docs/systemd-cgroups.md`, `docs/systemd-service-bridge.md` and
  `docs/gnome-desktop.md` (the udev/procd hotplug paragraph). Also update the CLAUDE.md
  "Dual-init" section.

## Verification

- **Host checks.**
  - `scripts/checkpatch.pl --no-tree --no-signoff` on patch 130
  - `make package/system/procd/compile V=s`, then the same for `systemd-openwrt` and
    `systemd-openwrt-services`
  - `python3 -B scripts/tests/test-systemd-service-bridge.py`
  - `git diff --check`
  - New `scripts/tests/test-procd-units.py`: build a test harness from the procd tree, like the
    bridge test does, that turns sample `service set` blobs (dnsmasq, uhttpd, sysntpd jail,
    respawn_policy, a one-shot task) into the unit property list, and assert the mapping.
- **Image.** Build with `python3 scripts/build-and-publish.py build-only -j12 V=s`, which reserves a
  build number. Then run `python3 scripts/test-image-network.py --image <img.gz> --work-dir <new dir>`
  for DHCP/DNS/NAT/LuCI on the router+client VM pair.
- **Guest checks** (the existing scripts plus new assertions):
  - `systemd-guest-smoke.sh`, `systemd-cgroup-services-guest.py`,
    `systemd-service-bridge-guest.py`, `boot-readiness-guest.py`, `logd-journal-guest.py`,
    `gnome-desktop-router-guest.py`, `input-hotplug-monitor.py`
  - procd has no daemon children, and every running `service list` instance maps to an active
    `openwrt-*@*.service`
  - `service list` matches the current image field by field, apart from the new `systemd_unit`
  - changing a dnsmasq option through UCI and running `reload_config` restarts the unit
  - `kill -9` on dnsmasq gets a systemd restart, and a forced crash loop emits `instance.fail`
  - hot-adding a virtio disk runs `/etc/hotplug.d/block` and mounts it
  - QEMU `system_powerdown` reaches `/etc/rc.button/power`
  - device modes are correct for kvm, render, input and snd
  - with `-device i6300esb`, systemd owns `/dev/watchdog`, and stopping the pinger resets the VM
  - restarting procd recovers services
  - the GRUB procd recovery entry, actual flashing and failsafe still work
- **Not authorized here.** Deploying to the router, publishing feeds, or committing without an
  explicit request.
