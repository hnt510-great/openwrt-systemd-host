# Desktop input hotplug

USB mice and keyboards use the kernel HID drivers and evdev. procd handles
`/dev/input/eventN` using `input-support`'s `root:input 0660` rule. Native
systemd's devtmpfs can precreate these nodes at `0600`; procd assigns the
input group but does not change the mode of an existing node. seatd opens
input nodes as root, so both modes permit desktop input. Weston
opens these devices through libseat/seatd, processes their events with
libinput, and delivers pointer and keyboard events to Wayland clients.
The x86/64 kernel builds USB HID and generic HID in; the desktop package
also installs `kmod-input-evdev`.

Device discovery uses libudev-zero. Its `udev` monitor listens on netlink
group `0x4`, which requires notifications from the device manager after
device setup. Startup enumeration alone can discover an already connected
mouse but cannot register a newly plugged mouse. See the upstream
[hotplug requirement](https://github.com/illiliti/libudev-zero#hotplugging).

## procd notification bridge

`package/system/procd/patches/110-libudev-zero-hotplug-broadcast.patch`
integrates rebroadcasting into the existing device manager:

1. Receive kernel uevents from `NETLINK_KOBJECT_UEVENT` group `1`.
2. Reject userspace senders, truncated messages, and messages without a
   terminating NUL. Keep an unchanged copy of the original event.
3. Run the existing rules. Node creation and ownership changes run
   synchronously; hotplug scripts and firmware helpers use procd's queue.
4. Append a notification barrier behind the event's queued helpers.
5. When preceding helpers finish, send the saved event to group `0x4` in
   the parent process. Preserve all properties, including `SEQNUM`, without
   adding shell environment variables or starting a helper process.

This covers add, remove, and change events for all subsystems, including
events whose rules return early. libinput receives input-device add/remove
notifications and Weston updates its devices without a desktop restart.
The bridge waits for helper completion, including helpers returning an
error; it reports completion rather than guaranteeing successful setup.
Background work detached by a hotplug script cannot be waited for.

procd listens only to group `1` and checks the sender's netlink port ID is
zero. Consequently it cannot treat a group `0x4` rebroadcast as a new kernel
event or form a feedback loop. No listeners is normal (`ESRCH`); other
send failures are logged. Sending is nonblocking. Notifications have no
delivery acknowledgement, so consumers must still tolerate device removal
and queue pressure.

The same code runs under native systemd's `openwrt-procd.service`, normal
procd PID 1, and procd recovery. systemd-udevd remains masked in native
mode. This bridge does not add udev's rules engine or hardware database.

## Build and validation

```sh
scripts/checkpatch.pl --no-tree --no-signoff \
  package/system/procd/patches/110-libudev-zero-hotplug-broadcast.patch
make package/system/procd/compile V=s
make -j2 V=s
```

The integration test uses an already booted, disposable QEMU guest with
root SSH and a controller created with `-device qemu-xhci,id=hotplug-usb`.
Boot without USB input devices so they can be added after Weston starts.
Use the rebuilt firmware, virtual DRM display, and an isolated network.
Python/ctypes, libinput tools, `stdbuf`, and Weston clients must be present
in the guest. The test installs a temporary delayed input hook and creates
the `hotplugcheck` desktop account. Dispose of the guest after testing.

```sh
python3 scripts/tests/test-input-hotplug.py \
  --ssh-port TEST_LOOPBACK_SSH_PORT --identity TEST_SSH_KEY \
  --qmp /absolute/path/to/qmp.sock --output /absolute/path/to/results
```

The test checks two USB mouse, tablet, and keyboard add/remove cycles,
libudev API notifications, ready node permissions, completion of a
one-second hotplug helper, Wayland motion/button/scroll/key delivery with
the same Weston PID, rejection of a forged userspace kernel-group event,
and absence of duplicate rebroadcasts. Add `--no-desktop` to exercise the
notification path in procd recovery without starting Weston. Results and
raw/libudev/libinput/Wayland evidence are saved in the output directory.

Validated on 2026-10-12 with the fresh x86_64/glibc EFI image and
`procd 2026.10.07~6a22d396-r3`:

| Check | Native systemd | GRUB procd recovery |
| --- | --- | --- |
| Two mouse/tablet/keyboard add/remove cycles | Passed | Passed |
| libudev API add/remove notifications | Passed | Passed |
| Notification after delayed helper completion | Passed | Passed |
| Root/input ownership and restricted node access | Passed, mode 0600 | Passed, mode 0660 |
| Wayland motion, clicks, scrolling, and keys without Weston restart | Passed | Not exercised |
| Forged userspace event rejected; no duplicate broadcasts | Passed | Passed |

The full build and patch style check passed. The firmware checksum is
`6a0781383d245d8e8201246115398fcb9092f591ce52c989ae8f757a4c789430`
for `bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz`.
Detailed evidence is in
`/srv/openwrt-validation/openwrt-hotplug-validation-20261012/native-results/`
and `recovery-results/`. The `.config` and pre-existing tracked edits were
unchanged. The guest returned from recovery to native systemd with procd
services, LAN, and firewall active. The disposable VM was stopped and its
test SSH port closed; the combined report is `final-verification.json`
in the evidence directory. No physical device was flashed.

For a flashed device, inspect `cat /proc/bus/input/devices`,
`ls -l /dev/input/`, `libinput list-devices`, and, as root,
`libinput debug-events`. Native desktop logs are available through
`journalctl -u openwrt-desktop.service`; procd-mode logs use `logread`.
Physical USB ports, controllers, and the intended mouse still require a
test on the actual box.
