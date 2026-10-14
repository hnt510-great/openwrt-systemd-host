# Live desktop RDP validation

Validated on 2026-10-13 using the x86_64/glibc native-systemd image:

`bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz`

SHA256: `70fd59685451e9c23cf3f97b6f8a728c42fe72bf15bb01154fb985da1acf7aab`.

The implementation uses Weston 16.0.0 and FreeRDP 3.32.2 to share the existing
local desktop with mandatory TLS/NLA and a separate RDP password. It retains
the authenticated TLS VNC mirror and the existing account provisioning overlay.
It does not install GNOME or create independent remote desktop sessions.

The disposable VM uses KVM, q35/OVMF, two vCPUs, 3 GiB RAM, VirtIO VGA at
1920x1080, and USB keyboard/tablet devices. Host-forwarded SSH, RDP, and VNC
ports bind only to loopback. The Linux client is Debian FreeRDP 3.15.0 in an
isolated Xvfb display, with the server certificate's SHA256 fingerprint pinned.
VNC tests verify the public certificate and its IP identity with X509Plain.

| Check | Result |
| --- | --- |
| FreeRDP, Weston, desktop package builds and full `make -j4 V=s` | Passed |
| Config generation/listener boundary tests, shell syntax, diff and Weston patch checks | Passed |
| Clean boot of the exact final image; packaged RDP module matches | Passed |
| Desktop/RDP disabled by default; no preset RDP credentials or TLS private keys | Passed |
| RDP/VNC listeners limited to the LAN IPv4 address; no IPv6 listener | Passed |
| SAM owned by the desktop user, mode 0600; password supplied through stdin | Passed |
| Empty/mismatched setup passwords preserve existing credentials | Passed |
| Missing or publicly readable SAM prevents desktop startup | Passed |
| Valid NLA accepted; wrong/Linux passwords, anonymous TLS and legacy RDP rejected | Passed |
| Root and another user rejected even with valid NTLM records | Passed |
| 1280x800 client request retains the local 1920x1080 desktop | Passed |
| Local and RDP input control the same terminal; disconnect releases held Ctrl | Passed |
| Wayland and Xwayland GTK typing/clicks and clipboard text in both directions | Passed |
| Verified TLS VNC and RDP share the desktop simultaneously | Passed |
| Password rotation retains the desktop PID/certificate, rejects old password | Passed |
| Native reboot preserves credentials/account and restores sharing automatically | Passed |
| Actual GRUB procd recovery boot, automatic startup and authenticated sharing | Passed |
| Actual QEMU sysupgrade from recovery preserves account/home/SAM/TLS and restores sharing | Passed |

The upgrade used the rebuilt final image after an earlier clean-image test.
The final image was then tested again from a new clean disk. No copied firmware
modules were used for final acceptance. `sysupgrade -T` passed with the existing
x86 “Image metadata not present” diagnostic; the actual upgrade and subsequent
native-systemd boot also succeeded.

Runtime checks found and fixed independent VNC/RDP listener settings, multiple
mirrors, shared-seat input ownership, connection resize/finalization ordering,
and Xwayland processing clicks before pending motion. The desktop init script
also creates the root-owned sticky X11 socket directory in procd recovery,
which does not run systemd-tmpfiles.

## Performance boundary

The 30 Hz default is a target. The synthetic test changes the whole fullscreen
GTK drawing area every 33 ms at 1080p, samples the Linux client's pixels for five
seconds, and measures 20 keyboard-driven black/white screen changes. Results
include the client, Xvfb sampling and input injection overhead. They are not a
physical Intel or real LAN benchmark, and do not establish a guaranteed 30 fps.

| Measurement | Result |
| --- | --- |
| Observed frame changes | 22.8 fps |
| Input-to-pixel median / p95 | 69.5 / 79.3 ms |
| Weston CPU, one core = 100% | 60.7% |
| Guest LAN transmit rate | 5.39 Mbit/s |

[Raw benchmark results](/srv/openwrt-validation/openwrt-rdp-validation-20261013/benchmark-results.json).

## Remaining verification

Windows Remote Desktop and Remmina were not exercised. Physical Intel display,
USB behavior, real LAN latency, sustained workload performance and the optional
GL renderer remain hardware/runtime checks. No physical device was flashed.

Strict Kconfig `--fatalrecursive` still detects the existing
`luci-app-weechat -> weechat-full -> weechat-minimal -> luci-app-weechat` cycle.
The original pre-RDP configuration produces the same error. The full firmware
build passes; unrelated feed configuration was preserved.

[Setup and connection instructions](desktop.md).

Evidence is in
[`openwrt-rdp-validation-20261013`](/srv/openwrt-validation/openwrt-rdp-validation-20261013):
`image-audit.json`, `fresh-audit-results.json`, `acceptance-results.json`,
`apps-systemd-results.json`, `apps-procd-results.json`, `auth-results.json`,
`credential-results.json`, `native-results.json`, `recovery-results.json`,
`upgrade-results.json`, `benchmark-results.json`, and the `final-*.log` files.
The VM/client scripts and local/remote screenshots are retained. Disposable
VM disks, SSH keys and test passwords are removed after validation.

## Feed reproducibility

The Weston integration is committed separately in `feeds/video` as
`10def13`. The base revision, exact commit and affected paths are recorded in
`configs/desktop-rdp-feeds.json`; the corresponding feed patch is exported as
`patches/feeds/0009-video-weston-rdp.patch`. The main-tree desktop and FreeRDP
packages are committed independently. The commit preparation rechecked the
three desktop configuration regressions and shell syntax; it did not change
the runtime implementation or repeat physical deployment.
