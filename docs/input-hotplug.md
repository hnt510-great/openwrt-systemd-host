# Input hotplug in the GNOME desktop

The native-systemd profile uses systemd-udevd, native libudev and logind seat
handling. GNOME/Mutter receives input through its normal libinput/logind path.
The x86/64 kernel provides USB HID support; the desktop also selects
`kmod-input-evdev`.

udevd is the device-event receiver. Its OpenWrt integration forwards events
requiring `/etc/hotplug.d` processing to procd. procd retains its service and
hotplug APIs; native device ownership, tags and seat discovery follow udev
rules. See [native supervision](systemd-native-supervision.md).

## Inspection

On the native-systemd device:

```sh
systemctl status systemd-udevd
loginctl seat-status seat0
udevadm info /dev/input/event0
```

Choose an actual event node present on the device. Inspect the active user's
session and group/seat access rather than broadening input-device permissions.

## Acceptance scope

In a disposable GNOME guest or a separately authorized physical test, attach
and remove USB keyboard and pointer devices after the desktop has started.
Check node creation, udev tags, seat discovery and real application input,
then repeat with RDP or Moonlight connected. Keep the GNOME session alive and
verify that router services remain operational.

The current session architecture and available evidence are documented in
[GNOME setup](gnome-desktop.md) and [GNOME validation](gnome-desktop-validation.md).
This guide defines checks; it does not claim that an additional physical USB
hotplug test was run during documentation cleanup.
