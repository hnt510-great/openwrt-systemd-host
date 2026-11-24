# Samba file sharing

The x86_64 native-systemd desktop profile includes Samba 4, its client and
diagnostic utilities, LuCI Network Shares, and the Simplified Chinese
translation. `configs/samba4.config` contains the reusable selections.
NetBIOS, WSD discovery, Avahi discovery, and common VFS modules are enabled.
Active Directory domain-controller support is disabled.

Windows discovers the server through `wsdd2`; Linux and macOS discover its
`_smb._tcp` service through Avahi. The `avahi-utils` package provides tools to
find advertised SMB servers on the local network:

```sh
avahi-browse --resolve --terminate _smb._tcp
```

This lists server names, addresses, and SMB ports. To list a discovered
server's shared folders, use `smbclient -L <server-address> -U <username>`.
The router advertises itself as `OpenWrt` even before any shared folders are
configured. Share paths and access settings remain managed in LuCI.

Configure shared directories under **LuCI → Services → Network Shares**
(`/cgi-bin/luci/admin/services/samba4`). No directory is exported by default.
Choose the path, allowed users, guest access, and read/write permissions there.
For password-protected access, add a Samba password for an existing Unix user:

```sh
sudo smbpasswd -a builder
```

The Samba password is separate from the SSH/Unix password. Clients connect
using `\\192.0.2.1\<share-name>` after a share is configured.

On native-systemd images, systemd owns Samba through static
`samba4.service` and `samba4@.service` units. All Samba processes, including
forked workers, belong to the top-level `nas.slice` with `CPUWeight=100`.
This slice is a sibling of `openwrt.slice`; raising the router slice's weight
therefore does not also raise Samba's relative CPU allocation. This feature
does not change `openwrt.slice`'s weight.

`samba4.service` waits for `network-online.target` (the existing OpenWrt LAN
readiness provider), then generates and checks the configuration before starting the
selected foreground daemons. The template instances cover `smbd`, optional
`nmbd`/`winbindd`, and the alternative AD-DC `samba` daemon. UCI flags and
installed binaries decide which instances run. Each daemon has native crash
restart and cgroup cleanup; procd registers no Samba service in this boot mode.
The existing `extra.samba_nice` option is retained.

Use native lifecycle commands:

```sh
sudo systemctl status samba4.service samba4@smbd.service samba4@nmbd.service
sudo systemctl show samba4@smbd.service -p MainPID -p ControlGroup -p FragmentPath
sudo testparm -s
sudo smbclient -L 192.0.2.1 -U builder
```

Under `CONFIG_OPENWRT_SYSTEMD=y`, `/etc/init.d/samba4` (`samba4-native.init`)
exits 0 on `boot`/`shutdown` so the rc queue cannot start duplicate daemons or
deadlock against the native units, and unconditionally delegates runtime
operations and enablement to `/usr/libexec/samba4-systemd` (non-systemd targets
retain the original procd init script).

A native path watcher observes `/etc/config/{samba4,system,dhcp}` and
`/etc/samba/smb.conf.template`, including LuCI Save & Apply. An interface
hotplug hook requests the same update for the interfaces selected in Samba UCI
(`lan` by default). WAN/WAN6 changes do not restart a LAN-only Samba. Updates do not
start an inactive Samba group. The path watcher runs before `paths.target`;
the Samba group and reconfigure service wait for network readiness without
waiting for the full procd rc queue to finish.

`systemctl reload samba4.service` validates a temporary generated configuration
with `testparm` before replacing `/var/etc/smb.conf`. Invalid input keeps the
previous generated file and does not restart the daemons. A regular custom
`/etc/samba/smb.conf` is preserved and also validated. A successful reload
restarts the daemon instances to reconcile optional-daemon and AD-DC settings;
existing SMB connections may disconnect. Configuration-triggered restarts reset
the instance start budget; automatic crash recovery retains its 5-per-60-second
limit. The reconfigure service has no generic start limit, so several rapid
edits cannot permanently disable its path watcher. Scheduling an update requires a
suitable maintenance window. `systemctl stop samba4.service` stops all member
instances; `systemctl disable samba4.service` also disables its path watcher.
The group's active state describes configuration setup; inspect each daemon's
status for actual fileserver health. The `openwrt@samba4.service` compatibility
bridge is excluded and points callers to the native unit.

Package hooks do not transfer a running procd instance to systemd. For an
existing procd installation, native enablement and the ownership handover must
be scheduled explicitly after installation; do not start the native group
alongside a live procd Samba instance. New offline images enable both the group
and path watcher. Upgrades preserve native enablement, and native `try-restart`
only affects an already active native group. No physical installation or
handover is part of the source change documented here.

See [validation](samba4-validation.md) for checks and runtime limits.

To build the packages:

```sh
make -j4 package/feeds/packages/samba4/compile \
  package/feeds/packages/avahi/compile \
  package/feeds/packages/wsdd2/compile \
  package/feeds/luci/luci-app-samba4/compile V=s
```

For a physical installation, use the matching signed userspace APKs and any
missing userspace dependencies. Simulate the offline APK transaction before
installing it. No kernel package, firmware flash, or reboot is needed.
