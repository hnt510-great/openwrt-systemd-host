# Shared GNOME desktop

The x86_64/glibc native-systemd image runs one ordinary user's GNOME 51
Wayland session on VT7. Local display, GNOME Remote Desktop LAN RDP and
Sunshine/Moonlight share that session. OpenWrt continues to manage routing,
DHCP, firewall rules and the UCI/procd service interface.

## Configuration

Use the complete saved desktop configuration for a new checkout. In an
existing workspace preserve `.config`, merge `configs/gnome-desktop.config`
with `scripts/kconfig.pl`, and run `make defconfig`. The profile selects native
systemd, systemd-udev, GNOME Shell/session, Files, Terminal, Tweaks, the GNOME
portal, audio and input-method integration. Full builds use:

```sh
python3 scripts/build-and-publish.py build-only -j12 V=s
```

Firmware and matching signed APKs are under `bin/systemd`.

## Device setup

Create an ordinary account and set its password as described in
[multiuser setup](multiuser.md). As root, configure that existing account:

```sh
desktop-setup USER
desktop-rdp-setup USER
```

RDP credentials are provisioned through the helper, without embedding them
in firmware. Keyring startup uses a root-only bootstrap credential. Follow
[GNOME setup](gnome-desktop.md) for keyring changes and remote access.

The session can start before LAN is ready. Remote listeners follow the LAN
address without replacing the desktop. RDP uses LAN IPv4 TCP 3389. Configure
Sunshine separately and pair a Moonlight client; portal capture and explicit
KMS enrollment have different permission requirements. A desktop restart
closes its applications, so finish work before `/etc/init.d/desktop restart`.

## Applications and validation

- [Chinese input](desktop-ime.md) and [audio](desktop-audio.md)
- [Firefox](firefox.md), [Flatpak](flatpak.md) and [AppImage](appimage.md)
- [Virtual machines](virt-manager.md) and [libvirt storage](libvirt.md)
- [Current GNOME guide](gnome-desktop.md) and [validation](gnome-desktop-validation.md)

Validation records distinguish VM, physical hardware and remote-client
coverage. No new runtime acceptance is claimed by this documentation update.
