# OpenWrt service controls through systemctl

This optional compatibility bridge adds individual systemctl controls while
retaining procd supervision, UCI, LuCI, init scripts, and OpenWrt boot ordering.
It does not convert daemons to native systemd supervision.

## Building and enabling

In make menuconfig, under Global build settings, select Experimental
systemctl controls for OpenWrt services. This sets
CONFIG_OPENWRT_SYSTEMD_SERVICE_BRIDGE=y and selects systemd-openwrt-services.
It requires the native-systemd variant and defaults to off. Installing the
matching signed package also enables the bridge on a native-systemd
installation; start openwrt-service-bridge.service after online installation.
Recovery boots never start the bridge.
After upgrading the bridge package, restart that native unit to load the new
daemon. Before removing the optional package, disable it using the command
below. This version generates no units that need removal.

The existing openwrt-services.service still executes enabled rc scripts in
their original order. The bridge discovers executable init scripts on demand,
without sourcing or running them for discovery. It excludes dbus (use the
existing native dbus.service) and recovery-only umount. It generates no proxy
service units and starts no per-service observer processes.

## Commands

Use the reserved openwrt@NAME.service namespace:

    sudo systemctl start openwrt@dnsmasq.service
    sudo systemctl reload openwrt@network.service
    sudo systemctl restart openwrt@passwall.service
    systemctl status openwrt@dnsmasq.service
    systemctl is-active openwrt@dnsmasq.service
    sudo systemctl enable --now openwrt@cron.service
    sudo systemctl disable openwrt@cron.service
    systemctl is-enabled openwrt@cron.service
    systemctl list-units --all 'openwrt*.scope' 'openwrt*.slice'

Changes require root/sudo; status queries do not. The .service suffix is
optional for these CLI actions. Use separate commands for native and OpenWrt
units. These controls target the local system manager; user, remote, offline,
runtime-only enablement, dry-run, and asynchronous control modes are rejected.
Native unit commands retain their upstream behavior.

The systemctl integration forwards the supported verbs to the bridge, which
executes the original init-script action exactly once. In particular, restart
invokes the script's own restart handler, preserving firewall semantics and
PassWall's locks. A bridge failure returns an error without trying a second
control path. Scripts' nonzero exit codes are preserved.

Enable/disable uses the original rc actions and /etc/rc.d links. Plain
enable/disable does not start/stop a service; --now requests the corresponding
runtime action after successfully changing boot settings. LuCI and direct
init-script controls continue to work. Status reads current procd data and
explicit health adapters on demand; action notifications retain setup receipts.
Package additions are visible immediately without a generator or daemon reload.

## Status

Status comes from current procd instance data or an explicit adapter:

| State | Meaning |
| --- | --- |
| active, instances running | At least one procd instance is running; counts expose partial failure |
| activating | No instances currently running, with procd respawn enabled |
| active, configured with no instances | Procd has registered configuration/triggers without a daemon |
| active, setup completed | A setup action succeeded in this boot; no daemon is expected |
| inactive, exited successfully | A process exited with status zero without respawn; it is not a failed daemon |
| inactive | No registered/running service, or an observed stop |
| failed | Instances stopped without respawn, or the last action failed and the service is down |
| unknown | Inspection unavailable or no adapter exists |

Setup completion records do not assert that configuration remains healthy
forever. The explicit task list covers the setup scripts in the current image.
For procd-managed setup tasks such as sysstat and urandom_seed, completion
requires successful instance exit, rather than just successful registration.
Firewall status checks the live inet fw4 nftables table. Zram checks active
swap. PassWall and PassWall Server count live processes referencing their
separate runtime directories; this is process presence, not an upstream
connectivity test. Third-party legacy scripts without an adapter remain
controllable but report unknown health.

The reserved openwrt@NAME.service spelling is a CLI compatibility interface,
not a native systemd service unit. Direct D-Bus StartUnit/StopUnit operations,
native unit dependencies, show, and list-unit-files do not provide the bridge's
lifecycle semantics. Use the supported CLI actions or original init scripts.

Real processes appear in transient scopes beneath openwrt-SERVICE.slice, with
unit escaping applied to SERVICE (a literal dash becomes \x2d). Resource controls
belong on that slice, not on the reserved CLI spelling. The status display
separates live health from observed placement; unknown placement does not imply
that a daemon is unhealthy. Procd instance data also exposes the scope and
managed/inherited/pending placement for each execution.

The bridge never supervises daemons or migrates discovered PIDs. Cgroup
placement works independently of this optional bridge. See
[cgroup ownership and cleanup](systemd-cgroups.md) for delegation, legacy
scripts, resource policy, and failure handling. Journal/logread paths remain
authoritative; scope membership is not a promise of complete per-unit logging.

## Disabling and recovery

    sudo systemctl disable --now openwrt-service-bridge.service

This stops the bridge, leaving router processes and their scopes running.
Use LuCI or /etc/init.d/NAME ACTION while it is disabled. Re-enable the native
bridge unit to restore the CLI controls. Setup completion records survive
bridge restarts within the same boot; /run clears them on reboot.

The bridge intentionally does not kill action-worker descendants on shutdown:
legacy scripts can launch processes outside procd. Original service stop and
shutdown scripts retain responsibility for them. The bridge accepts only
validated installed service names and fixed actions, checks the Unix peer UID
for mutations, and never treats client data as shell code.

GRUB procd recovery, failsafe, sysupgrade guards, and signed/exact-ABI package
requirements are unchanged. Validate a complete image in a disposable VM
before considering physical deployment.

## Tests

Run python3 -B scripts/tests/test-systemd-service-bridge.py after building the
x86_64/glibc toolchain and target libraries. It builds a separate test binary
with explicit temporary-root and snapshot fixtures; production builds contain
neither override. It tests the actual binary, Unix transport, init actions,
state parsing, enablement, concurrency, and absence of proxy/generator actions.

The guest smoke test requires an explicit disposable-VM flag. Package and
host-test success do not establish complete-image or physical-router success.
See the [scope/slice image and VM validation record](systemd-cgroups-validation.md).
