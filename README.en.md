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

## After flashing: enable and use features

The complete desktop configuration now selects `luci-app-desktop-setup`.
On first visiting the LuCI overview, an authorized administrator enters the
**Desktop Setup Wizard**: Account → Features → Review → Result. It creates or
selects an ordinary account and enrolls GNOME/RDP, Moonlight, containers,
Flatpak and VM permissions. After completion or **Set up later**, automatic
entry stops; **System → Desktop Setup Wizard** remains available at any time.
See the [wizard guide](docs/desktop-setup.md). Manual setup remains below as an
alternative and for troubleshooting.

These steps assume an image built with this project's complete desktop
configuration. Replace the example account `alice` consistently with your own
username; `LAN-IP` means the device's actual LAN address. Run **root** commands
in the device's root console or SSH session, and **ordinary-user** commands
in that user's fresh SSH login or GNOME terminal. A reduced image needs its
missing packages from a matching APK repository before these features work.

### 1. Check boot mode, networking and the administrator password

Boot the default native-systemd GRUB entry. `procd recovery` is for recovery
and flashing, and cannot run GNOME. On first local-console access, as **root**:

```sh
cat /proc/1/comm
ip -4 addr
passwd
```

PID 1 should be `systemd`. Note the actual LAN address and open
`http://LAN-IP/`, or its configured `https://LAN-IP/`, from a computer on that
LAN to log into LuCI. Configure LAN/WAN port assignments, DHCP/PPPoE, DNS and
the time zone there, then verify name resolution and Internet access. Supply
port assignments, ISP credentials and wireless settings for your own network.

Plan and mount persistent data storage before initializing VM, container or
large application stores. `/tmp` is temporary, and a firmware configuration
backup is not a backup of VM disks or container data.

### 2. Configure this project's APK repositories

Features already included in the image can be configured immediately. To
install or update packages, first publish matching signed packages from the
build host as described in [LAN APK feeds](docs/lan-apk-feeds.md). Then, as
**root** on the device, edit `/etc/lan-apk-feeds.conf` and set `base_url` to
your real repository server. The checked-in `apk.example.invalid` is only an
example and cannot serve packages.

Once signing trust matches the image, run:

```sh
lan-apk-feeds-sync
apk update
```

GitHub feeds contain build recipes, not APK indexes to put into repository
configuration. This image needs matching glibc/native-systemd packages; do
not mix official musl or Alpine repositories into it.

### 3. Create an ordinary user and start local GNOME and RDP

Run as **root** on the device. The first two lines create a new account;
skip them if that account already exists:

```sh
useradd -m -U alice
passwd alice
usermod -aG sudo alice
desktop-setup alice
desktop-rdp-setup alice
```

The `sudo` group grants administrator access. `desktop-setup` configures and
starts GNOME on VT7, including unattended keyring unlock; an existing login
keyring prompts for its original passphrase. `desktop-rdp-setup` interactively
sets a separate RDP password and prints the TLS certificate fingerprint.

Use a connected monitor, keyboard and mouse for the local desktop; switch to
its virtual terminal with **Ctrl+Alt+F7** when needed. Connect an RDP client to
**`LAN-IP:3389`** with username `alice` and the RDP password just configured,
and verify the certificate fingerprint. RDP shares the local GNOME session.
Launch Files, Terminal, Tweaks and Firefox from the application overview.
**Ctrl+Space** switches Chinese input; existing Fcitx profiles retain their
configured shortcuts.

### 4. Enroll Moonlight, containers, Flatpak and VM access

For these features, enroll the same account as **root** on the device:

```sh
sunshine-setup alice --capture=portal
podman-rootless-setup alice
flatpak-user-setup alice
virt-manager-setup alice
uci add_list 'luci_podman.main.users=alice'
uci commit luci_podman
/etc/init.d/desktop restart
```

These steps configure Sunshine/audio and virtual input, subordinate IDs and
linger for rootless containers, per-user Flatpak storage, full local VM
management and the LuCI Podman account allowlist. `libvirt-admin` is a trusted
administrator role with privileges comparable to root. You can also select
the allowlisted account in **LuCI → Services → Rootless Podman → Configuration**;
add each account only once. The final desktop restart refreshes groups and the
session, closing desktop applications. Reconnect ordinary-user SSH sessions
as well to receive updated groups.

For RDP without Sunshine, still run `desktop-audio-setup alice` as **root**
to enable desktop playback and microphone access.

| Feature | First use |
| --- | --- |
| Moonlight streaming | Open **`https://LAN-IP:47990`**, set Sunshine Web credentials, add `LAN-IP` in Moonlight and complete PIN pairing. Initial portal capture may need a screen-selection grant in GNOME. For KMS, use `sunshine-setup alice --enable-kms` instead of portal enrollment, then restart the desktop |
| Desktop audio | Select the actual output/input in GNOME Sound; enable playback/microphone redirection in the RDP client. Moonlight uses Sunshine audio. Run `wpctl status` as the ordinary user to inspect devices |
| Rootless Podman | Run `podman info` as the ordinary user. In **Services → Rootless Podman**, select enrolled `alice`, pull an image, then create and start a container. See [Podman systemd](docs/podman-systemd.md) for Compose/Quadlet |
| Virtual machines | Enable CPU virtualization in firmware/BIOS. Start Virtual Machine Manager as the ordinary user, connect to `qemu:///system`, and choose an ISO, storage and existing `br-lan` bridge. **Services → QEMU Virtual Machines** manages existing domains rather than creating them; validate 3D separately; device-passthrough management is outside the current libvirt integration |
| GNOME settings | Use Settings/Tweaks for display, keyboard, mouse, sound and appearance; configure router networking in LuCI. Drivers/firmware alone do not configure Wi-Fi, Bluetooth or peripherals; see [hardware support](docs/desktop-kernel.md) |
| Distrobox and development | Create development containers as the ordinary user following [Distrobox](docs/distrobox.md). Included GCC, CMake, Python and development libraries need no service switch; see [native development](docs/native-development.md) |

In the **ordinary user's GNOME terminal**, add Flathub and install a first app:

```sh
flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install --user flathub org.gnome.Calculator
flatpak run --user org.gnome.Calculator
```

AppImage needs no background service. Download and verify an application as
the ordinary user, then run:

```sh
chmod +x ~/Applications/Application-x86_64.AppImage
~/Applications/Application-x86_64.AppImage
```

Replace the example with the actual file. See [AppImage](docs/appimage.md)
for library compatibility and storage requirements.

### 5. Configure routing extensions, sharing and DDNS

These features need your nodes, domains or shared directories; account
enrollment does not supply those settings:

| Feature | Enablement |
| --- | --- |
| Passwall | In **LuCI → Services → Passwall**, enter your nodes/subscription, DNS and routing policy, then save and enable it. This is the project's default proxy choice |
| Full cone NAT | Disabled by default. Select Full cone NAT under **Network → Firewall → General Settings**, then Save & Apply. It affects directly NATed traffic, not the behavior of a proxy exit |
| DNS nftset fast path | Used by the patched dnsmasq/nftables without a separate service switch. Passwall or your DNS rules must still configure nftset; see the [DNS fast path](docs/dnsmasq-nftset.md) |
| Samba | Configure real directories, allowed users and permissions in **Services → Network Shares**. No directory is shared by default. For password access, run `smbpasswd -a alice` as root; this password is separate from the system password |
| DDNS-Go | Configure and enable the service under **Services → DDNS-GO**, supply provider authorization, domain and address source, then inspect update logs |
| Logs and restart advice | **Status → System Log → Systemd Journal** shows logs. **Status → Restart Needed** scans processes after upgrades; scanning does not restart services |

**daed is an alternative to Passwall and is disabled by default.** Only when
switching to daed, run the following as **root**; do not combine it with the
steps for enabling Passwall:

```sh
uci set 'passwall.@global[0].enabled=0'
uci commit passwall
/etc/init.d/passwall stop
uci set daed.config.enabled=1
uci commit daed
/etc/init.d/daed enable
/etc/init.d/daed start
```

From the LAN, open **`http://LAN-IP:2023/`**, create the administrator account
immediately, then configure nodes, DNS and routing rules, confirming actual
interfaces such as `br-lan`. See [daed](docs/daed.md) for kernel requirements,
interlocks and switching procedures.

### 6. Check operation and manage upgrades

As **root** on the device, inspect system, desktop and kernel health:

```sh
systemctl --failed
/etc/init.d/desktop status
kernelctl check
needrestart
```

In a fresh **ordinary-user** session:

```sh
systemctl --user status podman.socket
podman info
virsh -c qemu:///system list --all
```

Test RDP/Moonlight input and audio, Chinese input, container networking, VM
startup, shares and DDNS as applicable. A running service alone does not
establish working functionality. The guides below contain further diagnostics.

With a working repository, `apk update` only refreshes indexes. Review installs
with `apk add --simulate PACKAGE` before the actual install. Follow
[kernel upgrades](docs/kernel-upgrade.md) and [APK preflight](docs/apk-upgrade-preflight.md)
for complete upgrades, trial boot and fallback. Back up home directories,
keyring/RDP/Sunshine configuration, Flatpak data, container volumes, VM
definitions and disks separately. Build-host scheduled maintenance remains
disabled and is not part of device first-boot setup.

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
