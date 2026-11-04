# OpenWrt: router and GNOME desktop

[简体中文](README.md) | **English**

A customized x86_64 OpenWrt tree combining routing, an ordinary-user GNOME
desktop, containers and local virtualization. It retains UCI, LuCI and procd
service interfaces while using glibc, APK and native systemd, and tracks the
Linux 7.3 mainline kernel series.

## Project features

| Area | Implementation |
| --- | --- |
| System | x86_64, glibc, signed APKs, merged `/usr`, native systemd; procd supplies OpenWrt service and recovery interfaces |
| Desktop | GNOME 51 Wayland session for an ordinary user, with Files, Terminal, Tweaks, Firefox ESR and Chinese input |
| Remote access | GNOME Remote Desktop LAN RDP and Sunshine/Moonlight share the same local desktop session |
| Audio and input | PipeWire/WirePlumber, PulseAudio compatibility, Fcitx5 and GNOME Kimpanel |
| Applications and development | Per-user Flatpak, AppImage, native development tools and Rust build support |
| Containers and virtualization | Rootless Podman, systemd/Quadlet, QEMU/KVM, libvirt, virt-manager and SPICE/VirGL |
| Routing extensions | Full cone NAT and a dnsmasq nftset netlink fast path; Passwall is the default proxy, with daed disabled as an optional alternative |
| Upgrades | ELF/ucode ABI checks, immutable APK identities, kernel generations and trial boot, publication gated by router upgrade preflight |

The main tree and feeds are maintained together. See the complete
[`configs/x86-64-systemd-desktop.config`](configs/x86-64-systemd-desktop.config),
[native systemd architecture](docs/systemd.md) and [GNOME desktop guide](docs/gnome-desktop.md).

## Get the source

The main tree, eight active feeds and Argon theme use ten private GitHub
repositories. The build account needs read access to each repository.
Authenticate on the build machine first:

```sh
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git
git clone https://github.com/hnt510-great/openwrt.git
cd openwrt
./scripts/feeds update -a
./scripts/feeds install -a
```

The `custom` feed links directly to `package/custom` in the main tree. Its
updater initializes the Argon theme submodule and checks upstream versions of
registered custom packages, so `update -a` can modify recipes. To regenerate
indexes only in an existing workspace, use `./scripts/feeds update -i -a`.

## Configure and build

Use a Linux host with OpenWrt build dependencies. The project keeps a complete
configuration and feature fragments. Restore the saved configuration only in
a new checkout:

```sh
cp configs/x86-64-systemd-desktop.config .config
make defconfig
make download
python3 scripts/build-and-publish.py build-only -j12 V=s
```

Preserve `.config` in an existing workspace and merge feature fragments with
`scripts/kconfig.pl` when needed. `build-only` reserves a kernel generation for
the complete build without publishing APKs or deploying a device. Native
systemd firmware and package outputs are under `bin/systemd/`.

Examples of individual package builds:

```sh
make package/custom/openwrt-desktop/compile V=s
make package/feeds/packages/qemu/compile V=s
```

A new complete image requires modules and development headers with the same
ABI. See [local build](docs/local-build.md) for configuration recovery, build
procedures and historical feed patch instructions.

## Feeds and maintenance

| Feed | Private repository | Purpose |
| --- | --- | --- |
| `packages` | [openwrt-packages](https://github.com/hnt510-great/openwrt-packages) | Libraries, applications, container and virtualization dependencies |
| `luci` | [openwrt-luci](https://github.com/hnt510-great/openwrt-luci) | Web management interface and local integration |
| `video` | [openwrt-video](https://github.com/hnt510-great/openwrt-video) | Graphics libraries, Mesa and display components |
| `routing` | [openwrt-routing](https://github.com/hnt510-great/openwrt-routing) | Optional routing and mesh software |
| `telephony` | [openwrt-telephony](https://github.com/hnt510-great/openwrt-telephony) | Telephony software and dependencies |
| `passwall_packages` | [openwrt-passwall-packages](https://github.com/hnt510-great/openwrt-passwall-packages) | Proxy cores, DNS tools and geodata |
| `passwall_luci` | [openwrt-passwall-luci](https://github.com/hnt510-great/openwrt-passwall-luci) | Passwall interface, service scripts and translations |
| `taskplan` | [openwrt-taskplan](https://github.com/hnt510-great/openwrt-taskplan) | DDNS-Go service and LuCI interface |

Each feed has its own commits. `scripts/feeds update` pulls private branches;
maintainers merge, validate and push original upstream changes before other
machines can receive them. Repository URLs, branches and original upstreams
are listed in the [source repository map](configs/github-source-repositories.json)
and [private GitHub hosting guide](docs/github-source-hosting.md).

## Device setup and documentation

Firmware contains no preset personal accounts, passwords, SSH keys or proxy
configuration. Create an ordinary account, then explicitly configure the
device with tools such as `desktop-setup USER` and `desktop-rdp-setup USER`.
See the following guides:

- [Accounts](docs/multiuser.md) and [GNOME sessions and remote access](docs/gnome-desktop.md)
- [Chinese input](docs/desktop-ime.md), [desktop audio](docs/desktop-audio.md) and [Firefox](docs/firefox.md)
- [Flatpak](docs/flatpak.md), [AppImage](docs/appimage.md) and [native development](docs/native-development.md)
- [Rootless Podman](docs/podman-rootless.md), [libvirt](docs/libvirt.md) and [VM management](docs/virt-manager.md)
- [Full cone NAT](docs/fullcone-nat.md), [DNS fast path](docs/dnsmasq-nftset.md) and [daed](docs/daed.md)
- [Kernel upgrades](docs/kernel-upgrade.md), [APK upgrade preflight](docs/apk-upgrade-preflight.md) and [publication readiness](docs/publication-readiness.md)

`docs/*-validation.md` separates source checks, VM results and physical-device
results. Historical records do not establish acceptance for every current
build. Current desktop evidence starts with [GNOME validation](docs/gnome-desktop-validation.md)
and its linked physical deployment reports.

APK publication and device deployment are separate operations. Production
publication requires a reachable router and passing upgrade preflight. Host
scheduled maintenance remains disabled. Personal overlays, credentials,
signing keys and build outputs are excluded from source repositories.

## License and provenance

This project is based on [OpenWrt](https://github.com/openwrt/openwrt) and retains
its GPL-2.0 license and upstream copyrights. Each package follows its own
recipe and source license declarations. See [COPYING](COPYING).
