# Native systemd supervision for NAS discovery services (`wsdd2` and `avahi-daemon`)

Alongside `samba4` (`samba4.service` and `samba4@.service`), `wsdd2` and
`avahi-daemon` run as native static systemd units in `nas.slice` on
native-systemd boots rather than as procd transient units under `openwrt.slice`.
See [Samba file sharing](samba4.md) for the `samba4` unit model.

## Architecture and ordering

- **`avahi-daemon.service`**:
  - D-Bus variant (`avahi-dbus-daemon`): `Type=dbus`, `BusName=org.freedesktop.Avahi`,
    `Requires=dbus.socket`, `After=dbus.service network-online.target`,
    `Before=samba4.service`, `Slice=nas.slice`.
  - No-D-Bus variant (`avahi-nodbus-daemon`): `Type=simple`,
    `After=network-online.target`, `Before=samba4.service`, `Slice=nas.slice`.
  - Starting after `network-online.target` ensures `/etc/init.d/system` has set
    the hostname and `lan` is up, while `Before=samba4.service` ensures
    `org.freedesktop.Avahi` is available on D-Bus before `smbd` registers
    `_smb._tcp`.
- **`wsdd2.service`**:
  - `Type=simple`, `Slice=nas.slice`, `After=network-online.target samba4.service samba4@smbd.service samba4@samba.service`,
    `PartOf=samba4.service`, `WantedBy=multi-user.target samba4.service`.
  - `ExecCondition=/usr/libexec/wsdd2-systemd condition` checks whether
    `samba4.service`, `ksmbd`, or legacy `samba` is active without the legacy
    `sleep 5` startup delay.
  - `wsdd2-config.path` triggers `wsdd2-reconfigure.service` (`StartLimitIntervalSec=0`)
    when `/var/etc/smb.conf`, `/etc/samba/smb.conf`, `/etc/ksmbd/ksmbd.conf`, or
    UCI `system`/`dhcp`/`ksmbd` configs change; `/etc/hotplug.d/iface/65-wsdd2`
    triggers reconciliation on `lan` interface updates when `wsdd2.service` is
    already active.

## Compatibility and lifecycle

- `/etc/init.d/wsdd2` and `/etc/init.d/avahi-daemon` exit 0 on `boot`/`shutdown`
  in native mode and delegate `start`/`stop`/`restart`/`reload`/`status`/`running`/`enable`/`disable`/`enabled`
  to systemd; in `procd` recovery boots they retain the original `USE_PROCD=1`
  implementation.
- `openwrt@wsdd2.service` and `openwrt@avahi-daemon.service` are excluded in
  `systemd-openwrt-services` and direct callers to the native units.
- Package upgrades (`PKG_UPGRADE=1`) never start a second daemon alongside an
  active `procd` listener; on first-time migration without
  `/etc/systemd/openwrt-migrated/<service>`, they enable the systemd unit when
  `/etc/rc.d/S[0-9][0-9]<service>` is present, then record the stamp so
  subsequent upgrades preserve manual `systemctl disable` choices. Fresh offline
  images enable the native units and pre-create the migration stamp.

## Tests

```sh
python3 -B scripts/tests/test-nas-systemd.py
python3 -B scripts/tests/test-samba4-systemd.py
python3 -B scripts/tests/test-systemd-service-bridge.py
```

The disposable guest suite is `scripts/tests/nas-systemd-guest.py --disposable-vm`.
