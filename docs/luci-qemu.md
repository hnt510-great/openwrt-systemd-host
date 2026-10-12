# LuCI QEMU management

`luci-app-qemu` adds **Services → QEMU Virtual Machines** at
`/cgi-bin/luci/admin/services/qemu`. The Simplified Chinese translation is
provided by `luci-i18n-qemu-zh-cn` (**服务 → QEMU 虚拟机**).

The page manages existing domains in the local `qemu:///system` connection.
It uses the existing [libvirt integration](libvirt.md); it does not create
domains, disks, networks or accounts. Define guests with virsh first.

## Operations and resources

- Start: `virsh --connect qemu:///system start UUID`.
- Shut down: `virsh --connect qemu:///system shutdown UUID`.
- Reboot: `virsh --connect qemu:///system reboot UUID`.
- List/status: read-only `virsh list --all --uuid --name` and bulk
  `virsh domstats --raw --state --cpu-total --balloon --vcpu --interface --block`.

The page refreshes every five seconds. CPU usage is the difference in
`cpu.time` divided by elapsed host uptime; 100% means one host logical core.
Disk and network rates sum counters across all guest devices. The first
sample, stopped guests, missing counters and counter resets show `—`.
Samples older than 30 seconds are discarded for rate calculation.

Memory shows QEMU's host resident set (`balloon.rss`) separately from
allocated guest memory (`balloon.current`). Neither claims to measure used
memory inside the guest. Statistics and operation semantics follow the
[virsh documentation](https://www.libvirt.org/manpages/virsh.html).

Shutdown and reboot are guest-cooperative requests. Their success means
libvirt accepted the request; actual completion depends on the guest's ACPI
or guest-agent support. The UI continues reporting actual domain state.
There is no forced shutdown/reset, undefine/delete, arbitrary command or
configurable remote URI in this package.

## Build and install

Enable `CONFIG_PACKAGE_luci-app-qemu=y` and, for Chinese,
`CONFIG_PACKAGE_luci-i18n-qemu-zh-cn=y`, then run:

```sh
make defconfig
make package/custom/luci-app-qemu/compile -j2 V=s
```

Dependencies select luci-base, rpcd-mod-ucode, ucode-mod-fs, virsh,
libvirt-daemon and coreutils-timeout. The existing libvirt package limits
this integration to the x86_64/glibc native-systemd variant.
The runtime dependency requires libvirt-daemon 12.8.0-r2 or newer for the
ACPI fake-reboot disk-lease fix. Build it with
`make package/custom/libvirt/compile -j4 V=s` and upgrade the matching daemon
APK along with the UI when installing on older firmware.

Matching APKs are emitted under `bin/systemd/packages/x86_64/base/` in this
checkout. Install both signed local APKs on compatible firmware:

```sh
apk add --no-network /tmp/libvirt-daemon-12.8.0-r2.apk /tmp/luci-app-qemu-1.0.0-r1.apk /tmp/luci-i18n-qemu-zh-cn-0.apk
/etc/init.d/rpcd restart
rm -f /tmp/luci-indexcache*
```

Re-login after restarting rpcd. Refresh browser assets when upgrading the
same package version. Selecting/building this package alone does not update
an already generated firmware image; run the image build to embed it.
Shut down guests before restarting virtqemud for the daemon upgrade. Existing
custom configuration, including `lock_manager = "lockd"`, should be retained.

## RPC permissions and validation

`luci.qemu.status` belongs to the read ACL; `luci.qemu.action` belongs to the
write ACL. Read-only LuCI sessions see disabled action buttons. The backend
accepts only canonical UUIDs and the three listed operations. All calls use
a fixed local URI and shell-quoted arguments. Read commands time out after
three seconds each, actions after five, with a one-second kill grace period.
On timeout, refresh the actual state before retrying. Connection errors
clear stale resource values and action controls.

Local regression checks:

```sh
python3 scripts/tests/test-luci-qemu.py
node scripts/tests/test-luci-qemu-view.js
```

The ucode tests use a fake virsh executable to exercise real parsing,
unusual names, missing/zero counters, empty lists, daemon errors, bounded
timeouts and rejection of injection/unrequested operations. View tests
cover rate/reset handling, unavailable data, read-only/busy controls and
safe text rendering. Target runtime and browser results are recorded in
[luci-qemu-validation.md](luci-qemu-validation.md).
