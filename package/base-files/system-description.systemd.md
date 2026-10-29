# OpenWrt Systemd Host

This custom x86_64 OpenWrt build combines a router with a general-purpose Linux
host. It uses glibc, APK packages and native systemd as the default PID 1.
Image-selected capabilities can include an ordinary-user Wayland desktop,
virtual machines, desktop applications, containers and native development tools.
OpenWrt's UCI, ubus, netifd and procd continue to manage the router stack.

## Discover this image

Start with `/etc/os-release` (a symlink to `/usr/lib/os-release`). Its `ID` is
`openwrt-systemd`, `ID_LIKE` includes `openwrt`, and `VARIANT_ID` is
`native-systemd`. `OPENWRT_SYSTEM_DESCRIPTION_FILE` points to this document.
`/etc/openwrt_release` provides the same display identity for OpenWrt tools;
its `DISTRIB_ID` retains the base distribution for compatibility.
`/etc/openwrt_version` retains the upstream-style build revision.

Recorded capabilities: **@OPENWRT_FEATURES@**.

`OPENWRT_FEATURES_SCOPE=image-build` means `OPENWRT_FEATURES` records image build
selections. `OPENWRT_FEATURES_SCOPE=deployment-snapshot` means the list records
installed capabilities checked when the metadata was deployed to an existing
system. Neither scope tracks running services or later package changes. Check
commands, packages, hardware, permissions and service status before assuming a
feature is currently usable.
The default init metadata describes the image; recovery can run procd as PID 1.
The build revision identifies base-files metadata, not necessarily the running
kernel or every installed package. Use `uname -r`, `apk info -v` and, when
installed, `kernelctl status` to inspect those independently.

Read-only discovery commands:

```sh
cat /etc/os-release /etc/openwrt_release
cat /proc/1/comm
uname -m; uname -r
ubus call system board
apk info
```

## Service and network ownership

With systemd as PID 1, use `systemctl` for native systemd units and `journalctl`
for their logs. `openwrt-ubusd.service`, `openwrt-procd.service` and
`openwrt-services.service` integrate the OpenWrt stack. Router services retain
their `/etc/init.d/<service>` interfaces and `/etc/config/<name>` UCI files.
Use `uci` and `ubus` to inspect router configuration and state; netifd owns
network interfaces. This build disables systemd-networkd and systemd-resolved.

The optional `systemd-openwrt-services` bridge also accepts controls such as
`systemctl status openwrt@dnsmasq.service`. This is a CLI compatibility
interface: procd still supervises those services, and UCI/init scripts remain
authoritative. The reserved `openwrt@NAME.service` spelling is not a native unit
for D-Bus calls or dependencies. Native SSH and D-Bus use `sshd.service` and
`dbus.service`. Procd processes use scopes beneath `openwrt-SERVICE.slice`;
resource policy belongs on the slice. Use both `journalctl` and `logread` as
appropriate for the service's logging path.

```sh
systemctl --no-pager status openwrt-procd.service openwrt-services.service
journalctl -b -n 50 --no-pager
uci show network
ubus call network.interface dump
```

## Optional capabilities

Feature names in `OPENWRT_FEATURES` have these meanings:

- `desktop`: ordinary-user GNOME Wayland desktop; inspect `desktop-setup`
  and `/etc/config/desktop` for provisioning and session configuration.
- `virtualization`: libvirt VM management; inspect `virsh -c qemu:///system list
  --all`, installed QEMU tools and `/dev/kvm`. KVM requires usable hardware
  support; virt-manager is available when separately selected.
- `flatpak`: ordinary-user Flatpak and desktop portal integration; inspect
  `flatpak --user list` in the intended user's session.
- `containers`: Podman container tools; inspect `podman info` as the intended
  user to determine the current rootful or rootless environment.
- `appimage`: manually launched AppImage support; application compatibility
  depends on its runtime and available libraries.
- `distrobox`: container-based distribution environments using the installed
  container engine; inspect `distrobox list` as the intended user.
- `native-development`: GCC and native library development files; inspect
  compiler, headers and libraries for the project being built.

### Desktop, remote access and audio

The GNOME desktop runs as an ordinary user, configured with
`desktop-setup USER` and `/etc/config/desktop`. GNOME Shell/Mutter manages the
local Wayland session. GNOME Remote Desktop provides RDP sharing of that same
session; `desktop-rdp-setup USER` configures its separate credentials. The
listener follows the LAN address and defaults to LAN IPv4 TCP 3389. Reconnecting
does not create another login session. This profile uses neither a VNC server
nor xrdp. Restarting the desktop closes its applications and remote connections.

`desktop-setup` provisions unattended GNOME keyring access for session startup.
Preserve the existing user keyring, root-only bootstrap credentials and RDP TLS
identity across upgrades; do not replace them to recover a remote connection.
Inspect the ordinary user's `gnome-keyring-daemon.service`,
`gnome-remote-desktop.service` and `openwrt-gnome-remotes.service` alongside
the root `openwrt-desktop.service`. Provisioning and an active listener alone
do not prove successful client authentication or screen sharing.

The desktop profile includes GNOME Files (`nautilus`), Terminal
(`gnome-terminal`), Settings (`gnome-control-center`) and Tweaks
(`gnome-tweaks`). Nautilus supports basic file browsing and filename search
without the optional LocalSearch indexer. Settings omits network, WWAN,
Bluetooth, Wacom, online-account, printer and color panels; router networking
remains under LuCI/UCI/netifd. Firefox ESR runs as the desktop user; profiles,
extensions and open tabs belong to that user.

Shell extension downloads use libsoup and GIO TLS. `libgio-gnutls`, built by
the `glib-networking` recipe, provides the TLS backend; `ca-bundle` provides
trusted certificates. Extension Manager delegates installation to Shell.
After adding a backend to a running installation, refresh caches with
`/usr/libexec/glib2-cache-update` and restart the desktop after the package
transaction if Shell has cached the unavailable backend.

With `openwrt-desktop-audio`, `desktop-audio-setup USER` enrolls the user for
PipeWire/WirePlumber playback and capture. Inspect `systemctl --user`,
`wpctl status` and `pactl info` in that user's session. GNOME RDP redirects
playback and a client microphone. Sunshine/Moonlight shares the same desktop
and audio after enrollment and client pairing. `sunshine-setup USER
--capture=portal` selects GNOME portal/PipeWire capture; `sunshine-setup USER
--enable-kms` explicitly enrolls KMS capture. Existing pairings and capture
preferences are preserved. Portal capture may require the user's screen
selection permission. GPU and codec support, playback, microphone and client
input require end-to-end checks; a render node or active service is insufficient.

When `openwrt-desktop-ime` is installed, the GNOME session supervises Fcitx5.
Its IBus compatibility frontend serves GNOME's native input path; the Kimpanel
Shell extension displays candidates, and GTK3/GTK4 modules support other
applications. Offline Chinese Pinyin, libime dictionaries and Chinese fonts
are included. Fresh profiles start in English; **Ctrl+Space** toggles Pinyin.
Type `nihao` and press Space to commit `你好`. Existing personal shortcuts,
profiles and dictionaries are preserved; inspect the user's Fcitx configuration
before assuming its trigger. Remote clients must forward the chosen shortcut
to the session. Do not start another Fcitx daemon; RDP reconnection alone does not
activate a newly installed session integration.

### Virtual machines, containers and development

Libvirt/QEMU supports KVM guests and virt-manager/SPICE consoles when selected.
Inspect the system connection (`qemu:///system`) separately from user sessions.
SPICE is the default guest audio path; QEMU PipeWire audio is optional and
requires access to the intended user's audio session. Installed virtualization
tools or an active daemon do not establish that any guest is running.

Podman supports rootful and explicitly enrolled rootless users, with native
systemd/Quadlet integration. User namespaces, subordinate IDs and persistent
container storage still need configuration. Distrobox uses the selected engine;
inspect each environment as its owning user. Flatpak applications use per-user
portals and permissions; AppImages depend on compatible runtimes/libraries.
Native development packages provide compilers, headers and pkg-config metadata;
kernel builds/modules require headers matching their intended kernel generation.

## Packages, storage and firmware

APK is the host package manager. Inspect `/etc/apk/repositories.d/` and
`/etc/apk/keys/` for this installation's repositories and signing keys. Use
signed packages from repositories matching this native-systemd/glibc build.
Kernel modules must match the running kernel's exact package ABI. Distribution
environments managed by Distrobox have their own userspace and package manager.

`lan-apk-feeds` generates the local repository list at boot and after APK
transactions from the installed kernel package ABI. The LAN origin is
`http://apk.example.invalid:8088`, with nine ABI-specific repositories plus the
protected kernel channel. It is served by nginx on the build host. Inspect the
generated list and router DNS before diagnosing unavailable packages. Upstream
snapshot feeds are not interchangeable with this native-systemd/glibc feed.
`apk update` refreshes indexes; it does not install or upgrade packages.

Inspect an upgrade with `apk upgrade --simulate` before committing it. Patched
APK validates managed kernel transitions and exact module coverage; missing
module migrations block the full upgrade. Where supported, an explicit
`apk upgrade --userspace-only --simulate` checks a userspace-only alternative
that preserves installed ABI-bound packages. Keep world constraints, signature
checks and kernel protection hooks intact.

OpenWrt rootfs/overlay and sysupgrade conventions still apply. Inspect `mount`
and `/etc/config/fstab` to determine the actual persistent storage and extroot
layout; `/var` may point into `/tmp`.

The supported firmware flashing path is the GRUB **procd recovery** entry.
`sysupgrade` permits image checks and configuration backups under native
systemd but blocks flashing there. Boot recovery before firmware flashing.

With `openwrt-kernel-upgrade`, signed APK kernel upgrades instead install
parallel versioned kernels, matching modules and headers under GRUB control.
Use `kernelctl status` and `kernelctl check` to inspect the running, pending,
known-good, previous-good and rescue states. A package installation does not
prove the new kernel has booted. A trial requires a deliberate reboot and
continuous health checks before promotion; the previous confirmed kernel and
original rescue provide fallback. Same-ABI package upgrades retain the installed
generation under the managed upgrade policy. Kernel upgrades and firmware
flashing are separate operations.

`needrestart --cached --json` and LuCI's Restart Needed page report cached
restart advice when installed. A fresh `needrestart` scan inspects replaced or
removed files and kernel/container state. Neither scan restarts workloads;
check report freshness and coverage before acting.

## Inspect the live system

This document describes the build's integration and available packages. Fixed
build revisions, kernel generations, guest inventories and running-service
snapshots become stale; query the machine before changing it. In particular,
the kernel ABI in a repository URL does not identify its booted generation.

```sh
uname -r
kernelctl check
# kernelctl status includes the full installed-generation inventory.
kernelctl status
apk info -e gnome-shell nautilus gnome-tweaks openwrt-desktop-ime
systemctl --no-pager status openwrt-desktop.service
loginctl list-sessions
findmnt /overlay
findmnt /boot
virsh -c qemu:///system list --all
ubus call network.interface dump
```

Run `systemctl --user`, `wpctl`, Flatpak and desktop application commands in
the intended ordinary user's session. Root's user manager is a different
context. Check RDP/Sunshine listener addresses with `ss -lntup` and preserve
LAN-only bindings when repairing remote access.
