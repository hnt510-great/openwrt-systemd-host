# OpenWrt Systemd Host

This custom x86_64 OpenWrt build combines a router with a general-purpose Linux
host. It uses glibc, APK packages and native systemd as the default PID 1.
Image-selected capabilities can include an ordinary-user Wayland desktop,
virtual machines, desktop applications, containers and native development tools.
OpenWrt's UCI, ubus and netifd manage the router stack; procd remains its
service API while systemd supervises the daemons.
Router additions include optional full cone NAT, a faster dnsmasq nftset path
and the opt-in daed transparent proxy beside the default Passwall.

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

systemd supervises router daemons. `openwrt-procd.service` runs
`procd --systemd=units`: each instance an init script registers becomes the
transient unit `openwrt-SERVICE@INSTANCE.service` in `openwrt-SERVICE.slice`,
which owns exec, restart, limits, user/group, logging and stop. procd remains
the OpenWrt service API (ubus `service`, `system`, `hotplug.*`, triggers and
validation) and runs `/etc/hotplug.d` and `/etc/rc.button` handlers fed by
systemd-udevd. Instances using vrf, trace, bundles or descriptor passing stay
procd children in `openwrt-*.scope`, with a journal warning naming the reason.
Control services through `/etc/init.d/NAME`, LuCI or `ubus`; stopping a
transient unit directly bypasses procd's view. Put resource policy on the slice.
Service output goes to the journal; `logread` and LuCI's System Log read it
through a compatibility view limited to the UCI log buffer.

The systemd manager owns the hardware watchdog (`RuntimeWatchdogSec=30s`);
`ubus call system watchdog` reports owner `systemd`. The x86/64 configuration
selects no watchdog driver, so there is no `/dev/watchdog` unless one is
installed. Returning to procd supervision is a `procd --systemd -S` drop-in for
`openwrt-procd.service` together with `RuntimeWatchdogSec=0` and `RebootWatchdogSec=0`; recovery boots
always run procd as PID 1.

`openwrt-network-wait-online.service` holds `network-online.target` until
netifd reports its autostart, statically configured local interfaces (such as
`lan`) up; WAN, PPPoE or VPN outages do not hold it. After 120 seconds it logs
the interfaces still down and releases the target. Rootless Quadlets depend on
it; select other interfaces with a drop-in rather than editing the unit.

The default-on `systemd-openwrt-services` bridge accepts controls such as
`systemctl status openwrt@dnsmasq.service`. This is a CLI compatibility
interface that runs the init script, and UCI/init scripts remain
authoritative. The reserved `openwrt@NAME.service` spelling is not a native unit
for D-Bus calls or dependencies. Native SSH and D-Bus use `sshd.service` and
`dbus.service`. PID 1 refuses direct start/stop/restart/reload jobs on procd
instance units from other clients, with instructions to use this bridge or the
init script. Stopping `openwrt-SERVICE.slice` remains a deliberate whole-service
override that skips init-script hooks. The restriction takes effect after reboot
or `systemctl daemon-reexec` into the updated systemd.

```sh
systemctl --no-pager status openwrt-procd.service openwrt-services.service
systemctl --no-pager list-units 'openwrt-*@*.service'
journalctl -u 'openwrt-dnsmasq@*' -n 50 --no-pager
journalctl -b -n 50 --no-pager
uci show network
ubus call network.interface dump
```

## Configuration history and safe changes

When `uci-history` is installed (`command -v uci-history`), `/etc/config` and
the extra paths listed in `/etc/config/uci-history` are journaled as numbered
revisions with masked secrets. LuCI shows them under *System → Configuration
History*. Its agent instructions are in
`/usr/share/doc/uci-history/AGENT-GUIDE.md`; `uci-history --json commands`
prints the command schema and exit codes, and `uci-history guide` prints the
instructions. All commands need root: use existing access such as `sudo -n`
and never change sudoers or prompt for passwords.

Wrap configuration changes, especially remote ones touching `network`,
`firewall`, `dhcp`, `wireless`, `dropbear` or `sshd`, in a timed transaction:
**begin → change → verify → confirm**. An unconfirmed transaction is reverted
when its timer expires or at the next boot, so a lost SSH session recovers on
its own. Confirm only after verifying connectivity and service behavior
yourself, not because a command succeeded; on failure run `abort` or let the
timer expire. Start with `status`, and do not run a LuCI apply while a CLI
transaction is armed. Never include `--show-secrets` output in transcripts.

```sh
sudo -n uci-history --json status
sudo -n uci-history --json begin --timeout 300 --actor agent --note 'purpose'
# make, commit and reload the authorized UCI changes, then verify them
sudo -n uci-history --json diff
sudo -n uci-history --json confirm      # or: abort
sudo -n uci-history --json log --limit 20 --config network
sudo -n uci-history --json restore REV --config network --timeout 300 --dry-run
```

## Router additions

These are off by default or transparent; inspect UCI and the running kernel
before assuming one is active.

- **Full cone NAT**: `firewall.@defaults[0].fullcone='2'` (LuCI *Network →
  Firewall*, "Enable full cone NAT") followed by `fw4 reload` makes IPv4 UDP
  masquerading endpoint-independent. It needs a kernel generation built with
  `CONFIG_NF_NAT_MASQUERADE_FULLCONE`; an older kernel masquerades normally.
  When active, `srcnat_wan` contains `masquerade fullcone`. Mode `1` and
  `fullcone6` rely on an out-of-tree expression that is absent here; fw4 logs
  the failed probe and falls back.
- **dnsmasq nftset**: `dnsmasq-full` adds plain address-set elements over
  netlink and falls back to libnftables for everything else. It needs no
  configuration; libnftables errors are still logged as `nftset ...`.
- **daed**: an eBPF (tc) transparent proxy with a web dashboard, shipped
  disabled. Passwall stays the default, and the two must not run together:
  the daed init script refuses to start while `passwall.@global[0].enabled`
  is `1`, and stops daed if Passwall is enabled later. LuCI *Services → daed*
  controls `daed.config.enabled`; the dashboard listens on port 2023 and is
  reachable from LAN and WireGuard zones only. The first visitor creates the
  admin account. Dashboard state lives in `/etc/daed/wing.db`. daed needs a
  kernel with BTF; check `/sys/kernel/btf/vmlinux`.
- **ttyd**: with `ssl=1` and no explicit certificate, ttyd on port 7681 reuses
  uhttpd's `main.cert`/`main.key`, so LuCI's HTTPS terminal page is not blocked
  as mixed content. An explicit `option ssl '0'` is preserved.
- **PPP**: pppd runs in ujail as user `ppp` (uid 454) with only
  `CAP_NET_ADMIN`/`CAP_NET_RAW`. Hooks in `/etc/ppp/ip-up.d` and `ip-down.d`
  run with the same rights; a hook that needs root no longer gets it.
- **LAN discovery notrack**: firewall4 adds `upnp_ssdp_notrack`,
  `wsd_ipv4_notrack` and `wsd_ipv6_notrack` once, so LAN SSDP (UDP 1900) and
  WS-Discovery (UDP 3702) multicast is not conntracked. An existing section of
  the same name, including a disabled one, is kept; the LAN input policy still
  applies. Rules live in the `notrack_lan` chain.

```sh
uci -q get firewall.@defaults[0].fullcone
nft list chain inet fw4 notrack_lan
nft list chain inet fw4 srcnat_wan
uci show daed; uci -q get passwall.@global[0].enabled
/etc/init.d/daed status
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
without the optional LocalSearch indexer. A minimal `gvfs` provides Trash,
Recent, Network, Computer, FTP and SFTP; removable-media mounting (no
`udisksd`), SMB/DNS-SD, MTP, WebDAV and FUSE backends are absent.
Settings omits network, WWAN, Bluetooth, Wacom, online-account, printer and
color panels; router networking remains under LuCI/UCI/netifd. Firefox ESR
runs as the desktop user; profiles, extensions and open tabs belong to that
user.

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
On Gen9–Gen11 Intel GPUs the kernel loads HuC by default (GuC only
authenticates it; submission stays on execlists), which low-power VA-API
encoding needs for bitrate control. Check `dmesg | grep -i huc` and
`vainfo | grep EncSliceLP`; `i915.enable_guc=0` restores the upstream default.

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
requires access to the intended user's audio session. Libvirt drivers outside
QEMU and storage (network, interface, nwfilter and device passthrough)
report `VIR_ERR_NO_SUPPORT` instead of failing on absent daemon sockets.
Restarting `virtqemud` does not shut guests down. Installed virtualization
tools or an active daemon do not establish that any guest is running.

Podman supports rootful and explicitly enrolled rootless users, with native
systemd/Quadlet integration. User namespaces, subordinate IDs and persistent
container storage still need configuration. Distrobox uses the selected engine;
inspect each environment as its owning user. Flatpak applications use per-user
portals and permissions; X11-only Flatpak apps such as Steam receive a filtered
copy of the session's Xwayland cookie. 32-bit x86 programs need a kernel with
IA32 emulation; check with `zgrep IA32_EMULATION /proc/config.gz`. An
`Exec format error` from one means the running kernel predates it. AppImages
depend on compatible runtimes/libraries.
Native development packages provide compilers, headers and pkg-config metadata;
out-of-tree kernel modules build against `kernel-dev-headers`, which follows the
newest installed kernel (`/usr/lib/modules/<release>/build`).

## Packages, storage and firmware

APK is the host package manager. Inspect `/etc/apk/repositories.d/` and
`/etc/apk/keys/` for this installation's repositories and signing keys. Use
signed packages from repositories matching this native-systemd/glibc build.
Kernel modules ship inside each `linux-image-<release>` package; `kmod-*`
packages only enable autoloading and are independent of the kernel. Distribution
environments managed by Distrobox have their own userspace and package manager.

`lan-apk-feeds` generates the local repository list at boot and after APK
transactions. The LAN origin is `http://apk.example.invalid:8088`, with the
kernel package channel `kernel-upgrades` plus nine userspace repositories under
`current/`. It is served by nginx on the build host. Inspect the
generated list and router DNS before diagnosing unavailable packages. Upstream
snapshot feeds are not interchangeable with this native-systemd/glibc feed.
`apk update` refreshes indexes; it does not install or upgrade packages.

Inspect an upgrade with `apk upgrade --simulate` before committing it. An
explicit `apk upgrade --userspace-only --simulate` checks a userspace-only
alternative that keeps the installed kernel packages. Keep world constraints, signature
checks and kernel protection hooks intact. An APK upgrade or reinstall starts
an init script only where it is enabled; it does not start disabled services.

OpenWrt rootfs/overlay and sysupgrade conventions still apply. Inspect `mount`
and `/etc/config/fstab` to determine the actual persistent storage and extroot
layout; `/var` may point into `/tmp`.

The supported firmware flashing path is the GRUB **procd recovery** entry.
`sysupgrade` permits image checks and configuration backups under native
systemd but blocks flashing there. Boot recovery before firmware flashing.

With `openwrt-kernel-upgrade`, kernels are installed like a distribution's:
every kernel build is a separate `linux-image-<release>` package carrying its
modules, and `apk upgrade` installs the newest one next to the running kernel.
Its initramfs and GRUB entry are generated on installation, and it becomes the
GRUB default; it runs after a deliberate reboot. GRUB gives a new default three
boot attempts. A boot counts as good once the static local interfaces, LAN
addresses, persistent overlay, OpenWrt services and SSH are up; otherwise the
system reboots and, after three attempts, falls back to the previous kernel.
`kernelctl list` shows the running, default, fallback, known-good and rescue
kernels; `kernelctl set-default`, `rollback` and `remove` manage them. Only the
default (active or pending) kernel, its fallback and the image's original rescue
kernel are kept; older kernels are pruned automatically. A package
installation does not prove the new kernel has booted. Kernel upgrades and
firmware flashing are separate operations.

`needrestart --cached --json` and LuCI's Restart Needed page report cached
restart advice when installed. A fresh `needrestart` scan inspects replaced or
removed files and kernel/container state. Neither scan restarts workloads;
check report freshness and coverage before acting.

## Inspect the live system

This document describes the build's integration and available packages. Fixed
build revisions, kernel generations, guest inventories and running-service
snapshots become stale; query the machine before changing it. In particular,
an installed kernel package is not necessarily the booted kernel.

```sh
uname -r
kernelctl check
kernelctl list
# kernelctl status includes the full installed-kernel inventory.
kernelctl status
apk info -e gnome-shell nautilus gnome-tweaks openwrt-desktop-ime
systemctl --no-pager status openwrt-desktop.service
loginctl list-sessions
findmnt /overlay
findmnt /boot
systemctl --no-pager status openwrt-network-wait-online.service
virsh -c qemu:///system list --all
ubus call network.interface dump
```

Run `systemctl --user`, `wpctl`, Flatpak and desktop application commands in
the intended ordinary user's session. Root's user manager is a different
context. Check RDP/Sunshine listener addresses with `ss -lntup` and preserve
LAN-only bindings when repairing remote access.
