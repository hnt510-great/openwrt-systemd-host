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

```sh
systemctl --no-pager status openwrt-procd.service openwrt-services.service
journalctl -b -n 50 --no-pager
uci show network
ubus call network.interface dump
```

## Optional capabilities

Feature names in `OPENWRT_FEATURES` have these meanings:

- `desktop`: ordinary-user Weston Wayland desktop; inspect `desktop-setup`
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

## Packages, storage and firmware

APK is the host package manager. Inspect `/etc/apk/repositories.d/` and
`/etc/apk/keys/` for this installation's repositories and signing keys. Use
signed packages from repositories matching this native-systemd/glibc build.
Kernel modules must match the running kernel's exact package ABI. Distribution
environments managed by Distrobox have their own userspace and package manager.

OpenWrt rootfs/overlay and sysupgrade conventions still apply. Inspect `mount`
and `/etc/config/fstab` to determine the actual persistent storage and extroot
layout; `/var` may point into `/tmp`.

The supported firmware flashing path is the GRUB **procd recovery** entry.
`sysupgrade` permits image checks and configuration backups under native
systemd but blocks flashing there. Boot recovery before firmware flashing.
