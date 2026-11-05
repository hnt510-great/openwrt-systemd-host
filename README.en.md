# OpenWrt Systemd Host

[简体中文](README.md) | **English**

An x86_64 OpenWrt fork that runs one machine as a router, a GNOME desktop, and a
container and VM host. It keeps UCI, LuCI and the procd service API, but uses glibc,
signed APK packages and native systemd underneath, and tracks the Linux 7.3 mainline kernel.

## Key features

- **Base system**: glibc, signed APK packages, merged `/usr`, systemd as PID 1; GRUB keeps a procd recovery entry
- **Desktop**: GNOME 51 on local VT7, with RDP and Sunshine/Moonlight sharing the same session; Fcitx5 input, PipeWire audio, Firefox ESR
- **Apps and containers**: Flatpak, AppImage, rootless Podman/Quadlet, Distrobox, a native development toolchain
- **Virtualization**: QEMU/KVM, libvirt, virt-manager, SPICE/VirGL
- **Routing**: full cone NAT, a netlink fast path for dnsmasq nftset; Passwall by default, optional daed (eBPF, disabled by default)
- **Upgrades**: kernels ship as numbered packages with GRUB trial boot and fallback; publication runs an APK upgrade preflight against the real router

## Build

You need a Linux host with the
[OpenWrt build prerequisites](https://openwrt.org/docs/guide-developer/build-system/install-buildsystem).
The main tree, feeds and Argon theme are public GitHub repositories. Clone over HTTPS without signing in:

```sh
git clone https://github.com/hnt510-great/openwrt-systemd-host.git
cd openwrt-systemd-host
./scripts/feeds update -a     # also checks and bumps package/custom recipe versions
./scripts/feeds install -a
```

On a fresh checkout, build with the saved full desktop config:

```sh
cp configs/x86-64-systemd-desktop.config .config
make defconfig
make download
python3 scripts/build-and-publish.py build-only -j12 V=s
```

`build-only` reserves a kernel build number but does not publish or deploy anything.
In an existing workspace, keep your own `.config` and merge `configs/<feature>.config`
fragments with `scripts/kconfig.pl` as needed. To build a single package:

```sh
make package/custom/openwrt-desktop/compile V=s
```

Output goes to `bin/systemd/`. See [local build](docs/local-build.md) (Chinese) for more.

## Flash

The image boots with **UEFI only**. The root partition is about 8 GiB, so use a disk of 16 GB or more:

```
bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz
```

**Fresh install**: from another OS or a live USB, write the image to the target disk.
Replace `/dev/sdX` with the real disk; this erases the whole disk:

```sh
gunzip -c openwrt-x86-64-generic-squashfs-combined-efi.img.gz | sudo dd of=/dev/sdX bs=4M conv=fsync status=progress
```

**Already running this firmware**: systemd mode refuses to flash with `sysupgrade`.
Reboot into the `procd recovery` GRUB entry and run `sysupgrade <image>` there.
Routine upgrades normally don't need a reflash; see [Upgrade](#upgrade).

## First use

1. Boot the default GRUB entry, set the root password on the console, and check that
   `cat /proc/1/comm` prints `systemd`.
2. Open `http://LAN-IP/` in a browser, log in to LuCI, and set up WAN/LAN, DNS and the time zone.
3. The first LuCI login opens the **desktop setup wizard** (later available under
   **System → Desktop Setup Wizard**). Use it to create a regular user and enable GNOME/RDP,
   Moonlight, containers, Flatpak and VMs. See [desktop setup](docs/desktop-setup.md).

Or do the same by hand in a root shell (replace `alice` with your user name):

```sh
useradd -m -U alice && passwd alice && usermod -aG sudo alice
desktop-setup alice                    # start GNOME on VT7
desktop-rdp-setup alice                # set the RDP password, print the certificate fingerprint
sunshine-setup alice --capture=portal  # optional: Moonlight streaming
podman-rootless-setup alice            # optional: rootless containers
flatpak-user-setup alice               # optional: per-user Flatpak
virt-manager-setup alice               # optional: local VM management
/etc/init.d/desktop restart
```

How to connect:

| Feature | Use |
| --- | --- |
| Local desktop | Attach a monitor, keyboard and mouse; **Ctrl+Alt+F7** |
| RDP | `LAN-IP:3389`, user `alice`, the RDP password |
| Moonlight | Create the Sunshine account at `https://LAN-IP:47990`, then pair with a PIN in Moonlight |
| Containers / VMs | `podman`, LuCI **Services → Rootless Podman**; virt-manager on `qemu:///system` |
| Proxy | Add nodes in LuCI **Services → Passwall**; to switch to daed see [daed](docs/daed.md) |
| Full cone NAT | Tick it in LuCI **Network → Firewall → General Settings** |

## Upgrade

The device installs and upgrades packages from a LAN APK feed published by the build host.
After publishing as described in [LAN APK feeds](docs/lan-apk-feeds.md), set the real
`base_url` in `/etc/lan-apk-feeds.conf` on the device, then:

```sh
lan-apk-feeds-sync
apk update
apk upgrade --simulate   # review the plan first
apk upgrade
```

A new kernel installs as an ordinary APK and gets a trial boot on the next restart. If it
fails three times, GRUB falls back to the previous kernel; `kernelctl check` shows the state.
Don't mix in official musl or Alpine repositories. Back up home directories, container
volumes and VM disks before upgrading. See [kernel upgrade](docs/kernel-upgrade.md) and
[APK upgrade preflight](docs/apk-upgrade-preflight.md).

## Documentation

- System: [native systemd](docs/systemd.md), [multi-user](docs/multiuser.md)
- Desktop: [GNOME](docs/gnome-desktop.md), [input methods](docs/desktop-ime.md), [audio](docs/desktop-audio.md), [hardware support](docs/desktop-kernel.md)
- Apps: [Flatpak](docs/flatpak.md), [AppImage](docs/appimage.md), [Podman](docs/podman-rootless.md), [Distrobox](docs/distrobox.md), [libvirt](docs/libvirt.md), [native development](docs/native-development.md)
- Networking: [full cone NAT](docs/fullcone-nat.md), [DNS fast path](docs/dnsmasq-nftset.md), [daed](docs/daed.md)
- Sources: [feed repository list](configs/github-source-repositories.json), [GitHub source hosting](docs/github-source-hosting.md)

Each feature has a matching `docs/*-validation.md` validation record.

## License

Based on [OpenWrt](https://github.com/openwrt/openwrt) and licensed under GPL-2.0; see
[COPYING](COPYING). Each package is distributed under its own license.
