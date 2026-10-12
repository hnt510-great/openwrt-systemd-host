# LuCI QEMU validation, 2026-10-11

The LuCI package, Chinese translation and libvirt 12.8.0-r2 packages were
built and installed using signed APKs in the isolated OpenWrt validation VM.
This was package-level validation on existing firmware, not a rebuilt final
firmware image or deployment to a physical router.

## Build and local checks

- `make defconfig` retained all existing enabled selections. Only
  `CONFIG_PACKAGE_luci-app-qemu=y` and
  `CONFIG_PACKAGE_luci-i18n-qemu-zh-cn=y` were added.
- `make package/custom/luci-app-qemu/compile -j2 V=s` passed.
- `make package/custom/libvirt/compile -j4 V=s` passed with the reboot patch.
- Six backend regression tests passed, including command injection rejection,
  hostile domain names, zero/missing counters, empty lists, daemon failure
  and a real three-second timeout of a hung fake virsh.
- View rate/reset/permission/text-rendering checks, JavaScript and ucode
  syntax checks, menu/ACL JSON parsing and PO validation passed.
- Kernel checkpatch was run on the libvirt patch with the upstream libvirt
  space indentation/comment style and absent submission signoff exempted;
  it reported no remaining errors or warnings.

The existing weechat Kconfig recursion and missing bmx7 feed warnings remain
unrelated to these changes. Package builds completed successfully.

## Target and browser checks

The test VM exposes SSH on loopback port 32222 and LuCI on loopback port
38080, with restricted QEMU user networking. Existing host system/session
domains were not operated on.

| Check | Result |
| --- | --- |
| Signed APK install and upgrade | Accepted without allowing untrusted APKs; existing qemu.conf retained |
| Backend | Real `ubus call luci.qemu status` enumerates UUID/name/state and bulk virsh counters |
| Browser | Actual LuCI/Argon page rendered in Chinese with five-second polling |
| Start | Button booted both a minimal nested KVM guest and a full OpenWrt guest |
| Shutdown | Button gracefully shut down the ACPI-capable minimal guest; UI reported shut off |
| Reboot | After the libvirt fix, the full guest rebooted, emitted a libvirt reboot event and returned to running |
| Reboot evidence | Same QEMU PID before/after, and two Linux boot banners in the same serial log |
| Suspend/resume regression | virsh suspend → paused → resume → running, same QEMU PID |
| Disk protection | A second domain using the running guest's writable qcow2 disk was refused by QEMU's write lock |
| Lock configuration | `lock_manager = "lockd"` retained throughout final validation |
| Resource usage | Real CPU/RSS/allocated RAM, disk read/write and minimal guest network counters displayed |
| Unsupported counters | Guest without a network device displays unavailable network rates as `—` |
| HTTP ACL | Read-only session can read status but cannot call actions; anonymous status/actions denied |
| Invalid operation | Actual backend rejected `destroy` without affecting the running guest |

The full guest used a disposable copy of the existing OpenWrt firmware,
direct kernel boot, two vCPUs and 1 GiB RAM. Its console showed procd boot;
the outer router VM runs the native-systemd/libvirt integration. No virtual
machine creation, filesystem changes or console access features were added
to the LuCI page.

## Reboot defect discovered and fixed

Before the patch, both the minimal and full guests accepted `virsh reboot`
but then exited. The daemon journal recorded a duplicate disk lock request:
`Lockspace resource ... is locked`. This matches
[libvirt issue 892](https://gitlab.com/libvirt/libvirt/-/work_items/892).

`qemuProcessHandleShutdown()` sets `pausedShutdown` during ACPI fake reboot;
the STOP handler retains the disk lease in that case. The package patch
skips reacquiring that same lease in `qemuProcessStartCPUs()`. Ordinary
start/suspend/resume paths still acquire leases. No lock manager was disabled.
The page requires `libvirt-daemon>=12.8.0-r2` so older affected daemons cannot
satisfy the APK's dependency.

## Artifacts and limits

Signed APKs in `bin/systemd/packages/x86_64/base/`:

- `luci-app-qemu-1.0.0-r1.apk`
- `luci-i18n-qemu-zh-cn-0.apk`
- `libvirt-12.8.0-r2.apk`
- `virsh-12.8.0-r2.apk`
- `libvirt-daemon-12.8.0-r2.apk`

Build, ACL, lifecycle and disk-lock logs and a screenshot are retained under
`/srv/openwrt-validation/luci-qemu-validation-20261011/`. The nested guests and
outer validation VM are shut down after testing. Unrelated local files and
pre-existing host VMs are preserved.

The existing compressed firmware image has not been regenerated with these
new APKs. Runtime checks cover nested AMD KVM on the test VM; they do not
prove deployment, disk/network passthrough or operation on physical hardware.
