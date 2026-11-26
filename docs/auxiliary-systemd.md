# Native systemd supervision for auxiliary router services (`cron`, `nlbwmon`, and `ddns-go`)

On native-systemd boots, `cron`, `nlbwmon`, and `ddns-go` run as native static
systemd units in the top-level `auxiliary.slice` (`CPUWeight=100`, sibling of
`openwrt.slice` and `nas.slice`) rather than as procd transient units under
`openwrt.slice`.

## Architecture and boot ordering

- **`auxiliary.slice`** (`package/system/systemd-openwrt/files/auxiliary.slice`):
  - Top-level slice with `CPUWeight=100`, isolating background scheduling,
    conntrack accounting, and dynamic DNS updates from core routing (`openwrt.slice`)
    and NAS file sharing (`nas.slice`).
- **`cron.service`** (`package/utils/busybox`):
  - `Type=simple`, `Slice=auxiliary.slice`, `After=openwrt-services.service`,
    `WantedBy=multi-user.target`, `Also=cron-config.path`.
  - Ordering after `openwrt-services.service` guarantees that early rc scripts
    (`sysfixtime` `S00`, `boot`/`uci-defaults` `S10`, `system` timezone `S10`,
    and late rc scripts such as `wgserver` `S99` that populate `/etc/crontabs/root`)
    complete before `crond` scans `/etc/crontabs`.
  - `ConditionDirectoryNotEmpty=/etc/crontabs` skips starting `crond`
    when `/etc/crontabs` is empty (matching the original init script without
    marking the unit failed or spawning a control process).
  - `cron-config.path` watches `/etc/crontabs` and `/etc/config/system` and
    triggers `cron-reconfigure.service` (`StartLimitIntervalSec=0`) to restart
    or stop `cron.service` when crontabs or `cronloglevel` change.
- **`nlbwmon.service`** (`feeds/packages/net/nlbwmon`):
  - `Type=simple`, `Slice=auxiliary.slice`, `Nice=19`,
    `After=network-online.target`, `Wants=network-online.target`,
    `WantedBy=multi-user.target`, `Also=nlbwmon-config.path`.
  - Waiting for `network-online.target` ensures `netifd` is on ubus and LAN
    interface subnets are ready for `network_get_subnets`/`network_get_subnets6`
    without waiting for the entire `openwrt-services.service` rc queue.
  - `nlbwmon-config.path` watches `/etc/config/{nlbwmon,dhcp,system}` and
    triggers `nlbwmon-reconfigure.service` (`StartLimitIntervalSec=0`).
  - `/etc/hotplug.d/iface/30-nlbwmon` triggers `nlbwmon-reconfigure.service` on
    `ifup`/`ifupdate` only for interfaces referenced by `nlbwmon` `local_network`
    or `dhcp` sections when `nlbwmon.service` is active.
- **`ddns-go.service`** (`feeds/taskplan/ddns-go`):
  - `Type=simple`, `Slice=auxiliary.slice`, `User=ddns-go`, `Group=ddns-go`,
    `After=network-online.target`, `Wants=network-online.target`,
    `WantedBy=multi-user.target`, `Also=ddns-go-config.path`.
  - `ExecCondition=+/usr/libexec/ddns-go-systemd condition` runs as root to
    check UCI `ddns-go.@basic[*].enabled='1'` (since `/etc/config/ddns-go` is
    `0600`), keeping the service cleanly skipped when disabled by default
    (`option enabled '0'`).
  - `ExecStartPre=+/usr/libexec/ddns-go-systemd prepare` runs as root to
    create and `chown ddns-go:ddns-go /etc/ddns-go` and write `/run/ddns-go/env`
    before `ExecStart` runs unprivileged as `ddns-go`.
  - `ddns-go-config.path` watches `/etc/config/ddns-go` and triggers
    `ddns-go-reconfigure.service` (`StartLimitIntervalSec=0`), which starts,
    restarts, or stops `ddns-go.service` when `enabled` or CLI options change in
    UCI or LuCI.

## Compatibility and lifecycle

- `/etc/init.d/cron`, `/etc/init.d/nlbwmon`, and `/etc/init.d/ddns-go` exit 0
  on `boot` and `shutdown` under native systemd so `openwrt-rcS` never spawns
  duplicate procd instances, and delegate `start`/`stop`/`restart`/`reload`/`status`/`running`/`enable`/`disable`/`enabled`
  to `/usr/libexec/<service>-systemd`.
- `openwrt@cron.service`, `openwrt@nlbwmon.service`, and `openwrt@ddns-go.service`
  are excluded in `systemd-openwrt-services` and direct callers to the native
  units.
- Package upgrades preserve systemd enablement and restart only an active unit.
  Fresh offline installs create native unit links without contacting the host manager.

## Tests

```sh
python3 -B scripts/tests/test-auxiliary-systemd.py
python3 -B scripts/tests/test-systemd-service-bridge.py
```
