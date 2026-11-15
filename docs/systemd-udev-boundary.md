# Device management boundary on native-systemd OpenWrt

`systemd-udev` 262-r14 installs a reviewed distribution subset of systemd v262's
`rules.d/99-systemd.rules.in`. It restores device units, including
`dev-tpmrm0.device`, without transferring router policy to systemd.
The installed file is `package/system/systemd/files/99-systemd.rules`.
Keep it explicit and review upstream changes on systemd upgrades; do not copy
upstream rules wholesale or silently filter them with installation-time sed.

## Ownership and event flow

- netifd owns network naming/configuration, addresses, routes and device network
  parameters. A network `.device` reports presence, not carrier or IP readiness.
- fstools owns early root/overlay and UCI mount policy; block/blockd handle later
  mount and autofs decisions. A block tag does not request a data-volume mount.
- systemd owns service lifecycle, dependency graphs and generic device state.
- devtmpfs creates base nodes; udev applies properties, permissions and seats.
- procd retains ubus/UCI, init scripts, hotplug handlers and recovery. In units
  mode it ignores ordinary raw device events and receives selected processed
  events through `90-openwrt-hotplug.rules` -> `openwrt-udev-forward` ->
  `procd.udev` -> `hotplug-systemd.json` -> `/etc/hotplug.d/`. Synthetic button
  events remain direct. Ordinary `hotplug.json` remains for other modes.

The forwarder normalizes DEVNAME; hotplug-call derives DEVICENAME from DEVPATH.
netifd independently listens to rtnetlink and network uevents. These listeners
are not alternate network configuration managers.

## Rule disposition

Line numbers below refer to the generated upstream v262 `99-systemd.rules`
(backlight template lines are identified separately). No net-setup-link,
automatic driver-loading or persistent-storage rules are added by this change.

| Upstream lines | Disposition and reason |
| --- | --- |
| 10, 98 | Keep remove/end control flow; udev/PID 1 still process removal. |
| 12, 14, 15 | Keep serial/hypervisor tty and vport tags plus unusable 8250 guard. Do not add getty ownership; numeric VTs are not matched by the serial rule. |
| 17, 19, 21 | Keep passive PTP, MTD and UBI visibility. No clock, flash or volume operations. |
| 23 | Tag ordinary block devices, excluding dm-* pending a complete DM metadata/event contract. |
| 27, 31, 35 | Exclude DM_NAME, DM disable-flag import and CRYPT superblock guards. Current rules do not generate DM_NAME/DM_UUID/ID_FS_USAGE; missing properties must not strand devices at READY=0. |
| 38, 39 | Keep md guards for absent array_state and empty/clear/inactive states. No RAID assembly. |
| 42, 45 | Keep empty-loop and disconnected-NBD guards. Applications still attach backing storage. |
| 54 | Keep non-loopback net tag and alias; no rename, address or route writes. |
| 55-56 | Keep Bluetooth tag, alias and system/user targets; no new daemon. |
| 58 | Keep conditional smartcard targets. Reader-property generation and pcscd are not supplied here. |
| 59 | Keep bridge from existing security-device tags; identification is separate. |
| 60 | Keep controlC sound targets. This neither starts a second audio server nor proves every PCM node ready. |
| 62, 63, 64 | Keep printer-subsystem, USB lp and USB printer-interface notifications to the same targets. |
| 66 | Keep UDC target notification; no gadget or USB-network configuration. |
| 69 | Exclude direct systemd-sysctl execution. It bypasses the service mask and overlaps OpenWrt boot/hotplug sysctl and netifd writes. |
| template 74, 75 | Leave backlight/keyboard-backlight save/restore disabled. No new brightness policy. |
| 73, 74, 75 | Exclude all rfkill restoration properties/path lookup/socket activation. RFKILL=disabled does not remove these upstream rules; GNOME's separate uaccess rule remains. |
| 78, 79 | Keep FUSE/configfs module notifications to existing canonical API-filesystem mount units. These are not root/overlay mounts; their existing modprobe@ dependency is a documented module-loading exception. |
| 83, 84 | Keep TPM RM and raw TPM tags; RM appearance wants tpm2.target. Neither tag proves credential decryption will succeed. |
| 92-93 | Exclude automatic optical GPT loop creation. Existing installer/preinit logic owns that path. |
| 96 | Exclude automatic host machine-tag mutation. |

## Readiness, replay and consumers

`systemd` tag, `seat` and `uaccess` are different contracts. READY=0 prevents
systemd readiness, not OpenWrt hotplug delivery. WANT properties add dependencies;
consumers requiring ordering or removal coupling must declare it themselves.
A `.device` is not proof of a working TPM operation or a configured network.

Procd requests one full device add replay per boot after its ubus endpoint exists;
its 45-second escape writes the replay marker even on failure. The marker means
boot may continue, not every handler succeeded. Desktop coldplug performs an
additional targeted replay. `udevadm settle` waits for udev, not the procd script
queue. The upstream trigger unit is packaged but not enabled by default; an
After= reference alone does not pull it in. Blockd also scans existing disks.

Do not introduce another global replay, settle gate or deduplication daemon.
Handlers must tolerate repeats. Tags do not themselves emit extra kernel events,
but RUN commands execute again; v262 device.c also has WANT reconciliation for
already-known devices. Do not assume repeated add can never submit a start job.
Keep desktop r34's bounded TPM probe: this change deliberately does not restore
its former hard-coded Requires=dev-tpmrm0.device dependency. Router startup must
not acquire desktop/TPM dependencies. Logind seats, GNOME discovery and libvirt
nodedev enumeration continue through their existing paths; libvirt does not
acquire network/interface driver ownership.

## Validation and rollout

Run `python3 scripts/tests/test-systemd-udev-boundary.py`, relevant procd/desktop
regressions, the systemd package build, and inspect packaged/final-rootfs rules.
Use an isolated QEMU router/client pair with persisted swtpm state to check device
activation, credential decryption across cold boot, delayed TPM appearance and
absence, plus DHCP/DNS, routing/NAT and management access. Exercise spare devices
only: never unplug an active physical WAN/LAN or root disk for testing.

Before promotion, also check test NIC/data-disk removal, loop attach/detach and
sound replay for duplicate handlers/instances. Confirm FUSE/configfs use one
canonical mount each. Actual desktop/keyring startup and physical TPM/AP/WAN/LAN
acceptance remain separate from a device/credential probe. No throughput or long
soak matrix is required for this change. Any router outage, new startup wait,
root/overlay error or dependency cycle blocks promotion; do not extend timeouts
to hide failures. See [validation](systemd-udev-boundary-validation.md).
