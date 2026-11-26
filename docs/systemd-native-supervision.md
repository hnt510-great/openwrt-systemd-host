# systemd supervision of OpenWrt services

In the native-systemd variant, procd no longer starts router daemons itself.
`openwrt-procd.service` runs `procd --systemd=units`: every instance that an
init script registers through `procd.sh` becomes a transient systemd service,
udevd owns device events, and the systemd manager owns the hardware watchdog.
procd remains the OpenWrt service API. Init scripts, UCI, LuCI, `reload_config`,
`service list` and the `hotplug.*` ubus objects keep working unchanged.

The normal init is systemd. The native OpenWrt failsafe console is started by
preinit. See [systemd boot](systemd.md) for the boot sequence and
[historical validation](systemd-native-supervision-validation.md) for past builds.

## Who does what

| Function | Owner in native boot |
| --- | --- |
| exec, restart, resource limits, user/group, logging, stop | systemd transient service |
| uevents, `/dev` permissions, device coldplug | systemd-udevd |
| `/etc/hotplug.d/*`, `/etc/rc.button/*` | procd, fed by udev |
| hardware watchdog | systemd manager (`RuntimeWatchdogSec=30s`) |
| ubus `service`, `system`, `hotplug.*`, triggers, validation | procd |
| preinit and failsafe shell | OpenWrt early init |

## Units

An instance `INSTANCE` of service `SERVICE` runs as
`openwrt-SERVICE@INSTANCE.service` in `openwrt-SERVICE.slice`:

```sh
systemctl list-units 'openwrt-*@*.service'
systemctl status 'openwrt-dnsmasq@*'
journalctl -u openwrt-uhttpd@instance1.service
```

The default-on [service control bridge](systemd-service-bridge.md) uses
`openwrt@NAME.service` to run the init script. PID 1 accepts direct instance
jobs only from the main PID of `openwrt-procd.service`; other processes in its
cgroup are also refused. An unresolvable requester is refused. File-backed
services, including `openwrt-console@.service`, are unaffected.

| Action (network/netifd example) | Result |
| --- | --- |
| `systemctl start`, `stop`, `restart` or `reload openwrt-network@instance1.service` | Refused (exit 4), suggesting `systemctl VERB openwrt@network` or `/etc/init.d/network VERB`; no hooks skipped |
| Direct D-Bus, batch or varlink jobs; try/reload-or-* variants | Same PID 1 check; marked batches containing a refused instance queue no jobs |
| `systemctl show -P CanStart -P CanStop openwrt-network@instance1.service` | Both `no`; `RefuseManualStart/Stop` remain `no` so procd can manage instances |
| `systemctl kill -s KILL openwrt-network@instance1.service` | Crash/respawn, according to the instance restart policy |
| `systemctl stop openwrt-network.slice` | Allowed whole-service emergency override; skips init-script hooks |
| `systemctl restart openwrt-procd.service` | Dependency jobs stop instances; rc scripts recreate them |
| Stopped or never-started instance with executable init script | Refused with a "not running; procd creates the instances" message |

Example refusal:

```text
openwrt-network@instance1.service is procd instance 'instance1' of OpenWrt service 'network'; a direct stop would skip /etc/init.d/network. Use 'systemctl stop openwrt@network' or '/etc/init.d/network stop'.
```

The bridge suggestion is included only when its helper is executable. Each
refusal logs the requester's PID and comm in the unit journal. Use
`systemctl restart openwrt@network` for a normal restart with init-script hooks.
Plain missing names such as `systemctl restart netifd` print a read-only hint
and retain the native command's failure; they are never redirected.

`kill` with SIGTERM can be a clean exit under `Restart=on-failure`, so it need
not respawn. `set-property`, `reset-failed`, `clean`, `freeze`, `thaw`, isolate
and shutdown keep their existing behavior. Fallback `openwrt-<id>.scope`
children (vrf, trace, bundle, passed descriptors) remain supervised by procd;
stopping them follows procd's crash/respawn rules. The restriction was
introduced in `systemd` `262-r12` (current `262-r15`); no procd upgrade or
cgroup-layout change is needed.

`ubus call service list` adds `systemd_unit`, `systemd_placement` (`unit`) and,
while the unit is loaded, `systemd_state` and `systemd_substate` to each
instance. `running`, `pid` and `exit_code` come from the unit.

### Mapping of procd instance parameters

| procd parameter | Unit property |
| --- | --- |
| `command` | `ExecStart` (`Type=exec`); wrapped in `/sbin/ujail` or `seccomp-trace` exactly as procd would |
| `env` | `Environment` |
| `user`, `group` (no jail) | `User`, `Group`; with a jail, ujail switches credentials as before |
| `limits` | `Limit*` and `Limit*Soft`; an omitted half keeps procd's own limit |
| `nice` | `Nice` |
| `stdout`, `stderr`, `facility` | `StandardOutput`/`StandardError=journal` (else `null`), `SyslogIdentifier` (command name), `SyslogFacility` |
| `term_timeout` | `TimeoutStopSec` (doubled for jails, as in procd) |
| `respawn threshold timeout retry` | `Restart=always`, `RestartSec=timeout`, `StartLimitBurst=retry+1`, `StartLimitIntervalSec=threshold*(retry+1)`; `retry` 0 disables the limit |
| `respawn_policy` | `Restart=on-failure`, `RestartSec=min`, `RestartMaxDelaySec=max`, `RestartSteps` from the multiplier |
| no `respawn` | `Restart=no`, `ExitType=cgroup` (workers of a one-shot command keep the unit active) |
| `reload_signal`, `procd_send_signal` | `KillUnit` to the main process |
| `pidfile` | written by procd from `MainPID` |
| `netdev`, `file`, `data`, `watch`, triggers, validation | unchanged in procd; a changed instance is stopped and started as a new unit |

Every unit also has `BindsTo=openwrt-procd.service`,
`Before=openwrt-services.service` (shutdown runs the rc stop scripts while the
daemons are still up), `CollectMode=inactive-or-failed`, `KillMode=mixed` for
respawning instances (`control-group` otherwise), `TasksMax=infinity`,
`OOMPolicy=continue` and `IgnoreSIGPIPE=no`. Jailed instances get `Delegate=yes`.

Differences from procd's own supervision:

- A crash loop is counted in a sliding window of starts, not as consecutive
  short runs. The default `respawn 3600 5 5` gives up after six starts within
  six hours. procd still emits the `instance.respawn` and `instance.fail` ubus
  events; `respawn_count` is the unit's restart count.
- Stopping an instance ends its whole cgroup after the main process exits,
  instead of signalling only the main process.
- Instances that use `vrf`, `trace`, an OCI bundle, passed stdio or notify
  descriptors, or a jail console or setns still run as procd children in an
  `openwrt-*.scope`, with a journal warning naming the reason. So does any
  instance started while procd cannot reach the systemd manager.

### Daemons that call `setsid()`

systemd makes every service a session leader, so a daemon that unconditionally
calls `setsid()` or `setpgid()` at start fails with `EPERM`. procd's own
children are not group leaders, so this only appears in units mode. Pass the
daemon's "do not create a process group" option (such as `--no-process-group`,
as historically done for Samba before `samba4` moved to native static units in
`nas.slice`; see [samba4.md](samba4.md)) in its init script.

## Hotplug

udevd receives all kernel device events and creates and permissions the
nodes. `/usr/lib/udev/rules.d/90-openwrt-hotplug.rules` forwards events whose
subsystem has an `/etc/hotplug.d` directory (plus `usb-serial` and firmware
requests) to `/usr/libexec/openwrt-udev-forward`. In native units mode
(`procd` patch `150-systemd-udev-hotplug-queue.patch`), the forwarder checks
`/run/openwrt-hotplug/receiver.cap` (version 1 + current `boot_id`):

- **Queued mode (steady state)**: events are atomically committed to the
  root-private directory `/run/openwrt-hotplug/pending/` (capped at 2,048 items
  and 8 MiB with rate-limited overflow warnings and `(boot_id, SEQNUM)`
  deduplication), so udev workers never block waiting on `procd` or `ubusd`.
  `procd` attaches an `inotify` watch before scanning on connect and reconnect,
  moves one record at a time into `inflight/` before emitting `ubus_notify` or
  running `/etc/hotplug-systemd.json`, and retires it at the completion
  boundary. If `procd` crashes mid-handler, the interrupted record moves to
  `quarantine/` (never auto-replayed), deferring only subsequent events for the
  same device while other devices continue. Inspect state with
  `ubus call procd.udev queue_status` and resolve quarantined items explicitly
  with `ubus call procd.udev queue_resolve '{"id":"...","action":"discard|retry"}'`.
  Backlogged block events validate `DISKSEQ` (preserving `remove`), and expired
  or stale firmware requests are skipped safely.
- **Mixed-version legacy fallback**: if a newer `openwrt-udev-forward` runs
  while an older `procd` without `receiver.cap` is still live during an online
  upgrade, it falls back to `procd.udev event` until `procd` restarts.

`hotplug-call` handlers run in procd's serial queue outside udev's worker, so
long-lived helpers such as FUSE mounts survive. `DEVNAME` is passed without the
`/dev/` prefix, as the kernel reports it. Pure software/logic hotplug callers
(`iface`, `dhcp`, `firewall`, `ntp`, direct `/sbin/hotplug-call`, and
`ubus call hotplug.<subsys> call`) bypass udev and the queue.

The `button-hotplug` module's synthetic button events carry no device path and
are discarded by udev, so procd still reads those from the kernel and runs
`/etc/rc.button/*`.

On its first start in a boot, procd runs `udevadm trigger --type=devices
--action=add --settle`, as its own `udevtrigger` coldplug did, and reports
readiness afterwards (at most 45 seconds). A procd restart does not repeat it.

Device permissions and local device policies follow a single-writer model:
the `hardware-support` packages ship `60-openwrt-{audio,video,input,printer}.rules`
(and dvb, hidraw) beside their `hotplug.json.d` fragments: capture PCM nodes in
`audio-capture`, sequencer and MIDI nodes in `midi`, V4L2 nodes classified by
`v4l-id`. For `/dev/kvm` and `/dev/dri/renderD*`, udev defaults (`0666`) apply
unless `libvirt-daemon` is installed, in which case its
`65-libvirt-devices.rules` tightens them directly in udev (`0660`, `kvm`/`render`).
Desktop DRM autostart, audio user ACLs, and Sunshine `/dev/uinput` ACLs are
driven by package-owned `80-openwrt-*.rules` and paired systemd `.path`/oneshot
units (`openwrt-desktop-drm.path`, `openwrt-desktop-audio-acl.path`,
`openwrt-sunshine-uinput.path`). `hotplug.json.d` `makedev` rules are not used
in native mode; a package that needs a node permission must ship a udev rule,
and `scripts/audit-hotplug-merge.py` guards upstream/feed merges against silent
divergence. See [device management boundary](systemd-udev-boundary.md) and
[udev/hotplug migration validation](systemd-udev-hotplug-migration-validation.md).

## Watchdog

`/etc/systemd/system.conf.d/openwrt.conf` sets `RuntimeWatchdogSec=30s` and
`RebootWatchdogSec=10min`. `ubus call system watchdog` reports
`{"owner": "systemd", "timeout": 30, ...}` and rejects changes.

The current x86/64 configuration selects no watchdog driver (`ITCO_WDT`,
`SP5100_TCO` and `I6300ESB_WDT` are unset, and no `kmod-*-wdt` package is
selected), so there is no `/dev/watchdog` and procd was not pinging one either.
The setting takes effect once a driver is installed and loaded at boot;
reboot after adding one. Check with `systemctl show -p WatchdogDevice
-p WatchdogLastPingTimestamp`.

## Rolling back to procd supervision

Without reflashing, return to procd-supervised instances with two drop-ins and
a reboot:

```sh
mkdir -p /etc/systemd/system/openwrt-procd.service.d /etc/systemd/system.conf.d
cat > /etc/systemd/system/openwrt-procd.service.d/legacy.conf <<'EOF'
[Service]
ExecStart=
ExecStart=/sbin/procd --systemd -S
EOF
cat > /etc/systemd/system.conf.d/zz-procd-watchdog.conf <<'EOF'
[Manager]
RuntimeWatchdogSec=0
RebootWatchdogSec=0
EOF
reboot
```

Both settings belong together: procd and systemd must not both open
`/dev/watchdog`. Remove the two files and reboot to return to units mode. The
Native OpenWrt failsafe remains available via GRUB.

## Tests

```sh
python3 -B scripts/tests/test-systemd-service-bridge.py
python3 -B scripts/tests/test-procd-units.py
scripts/checkpatch.pl --no-tree --no-signoff package/system/procd/patches/130-systemd-transient-units.patch
```

`scripts/tests/procd-units-guest.sh` runs inside a disposable VM booted from the
image; see the validation record.
