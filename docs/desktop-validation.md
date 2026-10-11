# Desktop firmware validation

Validated on 2026-10-10 using the built x86_64/glibc EFI image.

Image: `bin/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz`

SHA256: `2f737dffbad34ce738d7a78b876c4f1023726905dbe82b5256224efcacd07057`

The existing 8 GiB root partition configuration is retained. The desktop uses
Weston 16.0.0 with its native VNC backend and CPU rendering.

| Check | Result |
| --- | --- |
| Narrow library, Weston, and desktop package builds | Passed |
| Full firmware build, `make -j1 V=s` | Passed |
| Image checksum and installed package audit | Passed |
| Fresh-image desktop disabled; no preset desktop login account or TLS key | Passed |
| Ordinary-user process UID/GID; private key mode 0600 | Passed |
| Certificate-verified VeNCrypt/X509Plain login | Passed |
| Incorrect password and root VNC login rejected | Passed |
| Root and passwordless desktop setup rejected | Passed |
| Local and remote display comparison at 1280 x 800 | 100% matching pixels |
| VNC mouse/keyboard and local QEMU keyboard/mouse in the same terminal | Passed |
| Terminal working directory is the configured user's home | Passed |
| Repeated setup and service restart retain the certificate | Passed |
| Firmware reboot starts the desktop automatically; TLS login works | Passed |
| Original configuration selections and unrelated local changes preserved | Passed |

The VM booted through OVMF with a virtual DRM display, USB keyboard/tablet,
and an isolated LAN. Its test account existed only in a disposable disk
snapshot. The VM was stopped, its test password removed, and password text
redacted from private test logs. The delivered firmware contains no test account.

Actual Intel HDMI/DisplayPort, physical USB devices, display hotplug, and
hardware performance still require testing after flashing the intended machine.
No physical device was flashed.

Required build fixes include staging GMP's pkg-config metadata, tracking
`edid-decode` in v4l-utils configuration dependencies, and fixing the native
static Perl relink while removing obsolete optional core database archives.
The PAM password-check helper retains the setuid mode required for ordinary-user
authentication. Weston VNC remains an optional package build setting.

[Setup and connection instructions](desktop.md).

Evidence: [complete validation results](/srv/openwrt-validation/openwrt-desktop-validation-20261010/final-validation.json),
[local/remote terminal screenshot](/srv/openwrt-validation/openwrt-desktop-validation-20261010/remote-input.png).
The reproducible VM test runner is [openwrt-desktop-validation-20261010/verify-final.py](/srv/openwrt-validation/openwrt-desktop-validation-20261010/verify-final.py).
