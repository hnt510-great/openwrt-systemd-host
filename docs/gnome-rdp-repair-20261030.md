# Physical RDP recovery, 2026-10-30

On `192.0.2.1`, RDP authentication succeeded but every connection ended with
`Failed to record monitor: ... Unknown monitor`. Mutter's `GetCurrentState`
returned no physical or logical monitors, despite the HDMI connector being
connected in sysfs.

The boot journal establishes the ordering failure: desktop coldplug completed
at 08:46:22, GNOME selected simpledrm/card0 at 08:46:24, and i915 initialized at
08:46:28. The firmware framebuffer disappeared during driver takeover and the
already running compositor retained no usable monitor. The existing DRM-only
udev trigger and settle could finish before the PCI GPU driver loaded.

`desktop-gpu-coldplug` now synchronously probes PCI display-controller aliases
with kmod, honoring module blacklists, before the existing DRM/input/audio
coldplug and settle. The desktop package declares kmod and advances to release
23. Module-loading failure propagates instead of silently starting GNOME on an
incomplete device inventory.

The helper and coldplug unit were copied to the physical machine with original
files backed up in `/root/rdp-repair-20261030/`. This is a direct runtime repair;
the installed APK version remains unchanged and no feed was published. The
user authorized one desktop restart. GNOME then selected i915/card1 as its
primary GPU and restored HDMI-1 at 1920x1080/60.

Validation:

- Shell syntax and `git diff --check` passed. A synthetic PCI inventory checked
  that display aliases are loaded, audio devices are skipped, blacklist flags
  are passed, and a module-loader failure stops the helper.
- The helper completed successfully on the physical machine.
- `make package/custom/openwrt-desktop/compile V=s` passed for release 23.
- A real FreeRDP connection remained active, displayed the desktop, and opened
  GNOME Overview through remote keyboard input. The server no longer reported
  `Unknown monitor`; the probe then disconnected intentionally.
- Fcitx and Sunshine services are active. Moonlight streaming was not retested.
- Boot ID, network/firewall/DHCP/desktop configuration hashes and APK world were
  unchanged; `kernelctl check` passed and no system units failed.

Private client logs, screenshot, probe and build log are under
`bin/deployment/rdp-repair/20261030/`. No physical reboot was performed, so the
next full-boot ordering remains a separate acceptance check.
