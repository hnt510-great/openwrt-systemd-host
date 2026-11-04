# systemd supervision of OpenWrt services

In the native-systemd variant, procd no longer starts router daemons itself.
`openwrt-procd.service` runs `procd --systemd=units`: every instance that an
init script registers through `procd.sh` becomes a transient systemd service,
udevd owns device events, and the systemd manager owns the hardware watchdog.
procd remains the OpenWrt service API. Init scripts, UCI, LuCI, `reload_config`,
`service list` and the `hotplug.*` ubus objects keep working unchanged.

Recovery boots (the GRUB *procd recovery* entry and failsafe) and stock images
are unaffected: there procd is PID 1 and supervises as before. Firmware
flashing still requires procd recovery. See [native systemd](systemd.md) for
the boot sequence and the [validation record](systemd-native-supervision-validation.md).

## Who does what

| Function | Owner in native boot |
| --- | --- |
| exec, restart, resource limits, user/group, logging, stop | systemd transient service |
| uevents, `/dev` permissions, device coldplug | systemd-udevd |
| `/etc/hotplug.d/*`, `/etc/rc.button/*` | procd, fed by udev |
| hardware watchdog | systemd manager (`RuntimeWatchdogSec=30s`) |
| ubus `service`, `system`, `hotplug.*`, triggers, validation | procd |
| preinit, failsafe, recovery, flashing | procd (unchanged) |

## Units

An instance `INSTANCE` of service `SERVICE` runs as
`openwrt-SERVICE@INSTANCE.service` in `openwrt-SERVICE.slice`:

```sh
systemctl list-units 'openwrt-*@*.service'
systemctl status 'openwrt-dnsmasq@*'
journalctl -u openwrt-uhttpd@instance1.service
```

The `openwrt@NAME.service` spelling of the optional
[service control bridge](systemd-service-bridge.md) is a different thing: it
runs the init script. Control services through `/etc/init.d/NAME`, LuCI, or the
bridge; stopping a transient unit directly bypasses procd's view of the
service until the next start.

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
calls `setsid()` or `setpgid()` at start fails with `EPERM` (Samba reports
`Failed to create session`). procd's own children are not group leaders, so
this only appears in units mode. Pass the daemon's "do not create a process
group" option in its init script; for Samba this is `--no-process-group` on
`smbd`, `nmbd`, `samba` and `winbindd` (samba4 4.24.5-r5, feed patch
`0030-packages-samba4-no-process-group.patch`). The option is harmless under
procd.

## Hotplug

udevd receives all kernel device events and creates and permissions the
nodes. `/usr/lib/udev/rules.d/90-openwrt-hotplug.rules` forwards events whose
subsystem has an `/etc/hotplug.d` directory (plus `usb-serial` and firmware
requests) to `/usr/libexec/openwrt-udev-forward`. It calls procd's root-only
`procd.udev` ubus object, and procd runs `/etc/hotplug-systemd.json`: the
`hotplug-call` handlers in procd's serial queue, outside udev's worker, so
long-lived helpers such as FUSE mounts survive. `DEVNAME` is passed without the
`/dev/` prefix, as the kernel reports it.

The `button-hotplug` module's synthetic button events carry no device path and
are discarded by udev, so procd still reads those from the kernel and runs
`/etc/rc.button/*`.

On its first start in a boot, procd runs `udevadm trigger --type=devices
--action=add --settle`, as its own `udevtrigger` coldplug did, and reports
readiness afterwards (at most 45 seconds). A procd restart does not repeat it.

Device permissions come from udev rules. The `hardware-support` packages ship
`60-openwrt-{audio,video,input,printer}.rules` (and dvb, hidraw) beside their
`hotplug.json.d` fragments: capture PCM nodes in `audio-capture`, sequencer and
MIDI nodes in `midi`, V4L2 nodes classified by `v4l-id`. For `/dev/kvm` and the
render, accel and kfd nodes udev's defaults (0666) apply, as they already did in
native boot. `hotplug.json.d` `makedev` rules are not used in this mode; a
package that needs a node permission must ship a udev rule.

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
GRUB procd recovery entry remains available in either mode.

## Tests

```sh
python3 -B scripts/tests/test-systemd-service-bridge.py
python3 -B scripts/tests/test-procd-units.py
scripts/checkpatch.pl --no-tree --no-signoff package/system/procd/patches/130-systemd-transient-units.patch
```

`scripts/tests/procd-units-guest.sh` runs inside a disposable VM booted from the
image; see the validation record.
