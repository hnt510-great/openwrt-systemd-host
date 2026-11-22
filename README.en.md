# OpenWrt Systemd Host

[简体中文](README.md) | **English**

<img width="1931" height="1085" alt="Screenshot From 2026-11-05 22-06-51" src="https://github.com/user-attachments/assets/5694540a-657b-4a43-9fa8-368ae20a1a75" />

An x86_64 OpenWrt fork that runs either as a standalone **pure router** or as a
combined **router, GNOME desktop, container, VM, and native development host**.
It keeps UCI, LuCI, netifd, and the procd service API while building on
**glibc, GCC 15, signed APK packages, and native systemd**, tracking the
**Linux 7.3 mainline kernel**.

## Key features

- **Base system & supervision**: glibc, GCC 15.3.0, signed APK packages (ELF/ucode ABI enforcement and interrupted-commit recovery via `apk-resume`), merged `/usr`; **systemd as the sole normal PID 1** (`procd --systemd=units` transient units, `systemctl openwrt@NAME.service` CLI bridge, native `nas.slice` / `auxiliary.slice` supervision, and a native OpenWrt `failsafe=true` GRUB console)
- **Composable profiles**: standalone pure-router config (`configs/x86-64-systemd-router.config`), full desktop config (`configs/x86-64-systemd-desktop.config`), and stackable fragments for GNOME core, Podman, Distrobox, headless virtualization, Konsole, Qt6 dev, daed, and the installer ISO
- **Desktop & media**: GNOME 51 on local VT7 with RDP and Sunshine/Moonlight sharing the same Wayland session; TPM2-sealed keyring credentials (`systemd-creds`, falling back to plaintext), RealtimeKit (`rtkit`) low-latency scheduling, Fcitx5 CJK input, PipeWire audio, Firefox ESR, Google Chrome, and optional KF6/Konsole terminal stack
- **Apps, containers & development**: Flatpak (both per-user and D-Bus/polkit-authorized system-wide installation, plus Xwayland cookie forwarding), AppImage, rootless Podman/Quadlet, Distrobox, and native development packages (`native-libs-dev`, `kernel-dev-headers`, Qt6 dev)
- **Virtualization**: QEMU/KVM, libvirt, virt-manager, SPICE/VirGL, OVMF (UEFI/Secure Boot), `swtpm` (TPM 2.0 for Windows 11), `virtiofsd`, PCI/USB passthrough, and per-guest nftables network filters
- **Routing & operations**: full cone NAT, dnsmasq nftset netlink fast path, LAN discovery `notrack`, unprivileged `pppd` (`ujail`), HTTPS `ttyd`, `irqbalance` per-netdev CPU pools; Passwall by default with optional daed (eBPF, disabled by default); built-in `uci-history` (Git-versioned config with timed auto-rollback), `needrestart`, and opt-in `router-audit` (disabled by default)
- **Installation & rolling upgrades**: hybrid BIOS/UEFI installer ISO with **signed offline optional component selection**; LZ4 squashfs fast rolling image packaging; parallel numbered kernel packages (`linux-image-*`) managed by `kernelctl` with 3-attempt GRUB trial boot and automatic fallback; evidence-based ELF type ABI diagnosis and live-router APK upgrade preflight before publication

## Build

You need a Linux host with the
[OpenWrt build prerequisites](https://openwrt.org/docs/guide-developer/build-system/install-buildsystem);
building the installer ISO also requires `xorriso`. The main tree, feeds, and
Argon theme are public GitHub repositories and can be cloned over HTTPS without
signing in:

```sh
git clone https://github.com/hnt510-great/openwrt-systemd-host.git
cd openwrt-systemd-host
./scripts/feeds update -a     # also checks and bumps package/custom recipe versions
./scripts/feeds install -a
```

On a fresh checkout, start from either baseline configuration:

```sh
# Full desktop + virtualization + containers + installer ISO
cp configs/x86-64-systemd-desktop.config .config
# Or standalone pure router (minimal native-systemd router baseline)
# cp configs/x86-64-systemd-router.config .config

make defconfig
make download
python3 scripts/build-and-publish.py build-only -j12 V=s
```

`build-only` reserves a kernel generation number and packages outputs without
publishing or deploying anything. In an existing workspace, keep your own
`.config` and merge `configs/<feature>.config` fragments with `scripts/kconfig.pl`
(such as `gnome-desktop-core.config`, `podman.config`, `distrobox.config`,
`virt-headless.config`, `konsole.config`, `qt6-dev.config`, `daed.config`, or
`installer-iso.config`):

```sh
./scripts/kconfig.pl + .config configs/installer-iso.config > .config.new
mv .config.new .config
make defconfig
```

To build a single package:

```sh
make package/custom/openwrt-desktop/compile V=s
```

Outputs go to `bin/systemd/`. See [local build](docs/local-build.md) and
[router decoupling plan](docs/systemd-router-decoupling-plan.md).

## Install

### Installer ISO (recommended)

The hybrid installer supports both **UEFI and legacy BIOS** boot; a target disk
of 16 GB or more is recommended. The ISO ships a clean base system plus a
**signed offline APK repository verified against `/rom/etc/apk/keys`**, allowing
you to select optional components (desktop, RDP, audio/IME, Flatpak, containers,
virtualization, browsers) during installation.

Write the ISO raw to a dedicated USB stick using Etcher, Rufus in **DD mode**,
or `dd` (replace `/dev/REPLACE_USB` with the actual USB device; this erases the
USB drive):

```sh
sudo dd if=bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-installer.iso of=/dev/REPLACE_USB bs=4M conv=fsync status=progress
sync
```

1. Boot from USB and choose **Install OpenWrt** (or **Install OpenWrt (serial console)**).
2. Pick the target disk and partition layout in the whiptail TUI: FAT32 ESP,
   read-only LZ4 squashfs root, writable `rootfs_data` (`ext4` by default, or
   `btrfs`/`xfs`), and optional extra data partitions.
3. Assign WAN/LAN interfaces by MAC, driver, and link status; configure
   networking, firewall, and root password (default LAN is `192.168.1.1/24`;
   WAN supports DHCP, PPPoE, static IP, or none).
4. Select optional offline components (preflight checks exact APK installed
   sizes against the overlay), and optionally create a regular user and
   configure GNOME startup. Confirm the summary to install:
   **the selected target disk is repartitioned and all existing data is erased.**
5. Remove the USB drive and reboot into the target disk (UEFI install does not
   require NVRAM boot entry edits).

In VMs, attach the same ISO as a **SATA CD-ROM** ahead of a writable target disk
(validated with **Standard VGA** in virt-manager) and eject it after install.
Rufus ISO mode and Ventoy are not supported. See
[USB/optical installer](docs/installer-iso.md) for details and `--answers`
unattended installation.

### Direct disk image

Alternatively, write `combined-efi` directly to the target disk from another OS
or live environment and boot via **UEFI** (replace `/dev/REPLACE_DISK`; this
erases the entire disk):

```sh
gunzip -c bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz | sudo dd of=/dev/REPLACE_DISK bs=4M conv=fsync status=progress
sync
```

> **Reinstallation & recovery**: systemd is the sole normal init and there is no `procd recovery` GRUB entry; `sysupgrade` is for configuration backup and restore (`-b`/`-l`/`-r`) only. Routine userspace and kernel updates are delivered through APK. To replace the whole firmware image, use the installer ISO or offline disk imaging and restore your configuration archive. GRUB provides a native OpenWrt `failsafe` preinit console for emergency recovery.

## First use

1. Boot the default GRUB entry and confirm `cat /proc/1/comm` prints `systemd`.
   Use the root password set in the installer, or set one on the console after
   direct disk imaging.
2. Open `https://LAN-IP/` (or `http://LAN-IP/`) in a browser, log in to LuCI,
   and adjust WAN/LAN, DNS, and time zone as needed.
3. Open **System → Desktop Setup Wizard** in LuCI to create or select a regular
   user and enable GNOME/RDP, Moonlight, containers, Flatpak, and VMs (or reuse
   the user created by the installer). See [desktop setup](docs/desktop-setup.md).

Or provision manually in a root shell (replace `alice` with your username):

```sh
useradd -m -U alice && passwd alice && usermod -aG sudo alice
desktop-setup alice                    # start GNOME on VT7 (add --no-autostart to disable autostart)
desktop-rdp-setup alice                # set the RDP password and print the certificate fingerprint
desktop-audio-setup alice              # optional: PipeWire audio
sunshine-setup alice --capture=portal  # optional: Moonlight streaming
podman-rootless-setup alice            # optional: rootless containers
flatpak-user-setup alice               # optional: per-user Flatpak
virt-manager-setup alice               # optional: local VM management
/etc/init.d/desktop restart
```

Quick reference:

| Feature | Use |
| --- | --- |
| Local desktop | Attach a monitor, keyboard, and mouse; **Ctrl+Alt+F7** |
| RDP | `LAN-IP:3389`, user `alice`, RDP password |
| Moonlight | Create the Sunshine account at `https://LAN-IP:47990`, then pair with a PIN in Moonlight |
| Containers / VMs | `podman`, LuCI **Services → Rootless Podman**; virt-manager on `qemu:///system` |
| Proxy | Add nodes in LuCI **Services → Passwall**; to switch to daed see [daed](docs/daed.md) |
| Full cone NAT | Enable in LuCI **Network → Firewall → General Settings** |
| Config history / rollback | LuCI **System → Configuration History** or `uci-history` (timed auto-rollback transactions) |
| Restart advice | LuCI **System → Restart Needed** or `needrestart` |

## Upgrade

Devices receive rolling userspace and kernel updates from a signed LAN APK feed
published by the build host. After publishing per
[LAN APK feeds](docs/lan-apk-feeds.md), set the real `base_url` in
`/etc/lan-apk-feeds.conf` on the device, then run:

```sh
lan-apk-feeds-sync
apk update
apk upgrade --simulate   # review the plan first (or --userspace-only to keep the current kernel)
apk upgrade
```

New kernels install alongside the running kernel as numbered
`linux-image-<release>` APKs and receive a 3-attempt GRUB trial boot on the next
reboot, automatically falling back to the previous kernel on failure; check
status with `kernelctl list` / `kernelctl check`. Live APK commits are protected
by `apk-transaction-guard` and resumed offline on next boot by
`apk-resume.service` if interrupted by power loss. Do not mix official musl or
Alpine repositories, and back up home directories, container volumes, and VM
disks before upgrading. See [kernel upgrade](docs/kernel-upgrade.md),
[APK upgrade preflight](docs/apk-upgrade-preflight.md), and
[APK transaction recovery](docs/apk-transaction-recovery.md).

## Documentation

- **System & init**: [native systemd](docs/systemd.md), [systemd-only plan](docs/systemd-only-plan.md), [router decoupling](docs/systemd-router-decoupling-plan.md), [service bridge](docs/systemd-service-bridge.md), [NAS & auxiliary supervision](docs/nas-systemd.md), [udev boundary](docs/systemd-udev-boundary.md), [multi-user](docs/multiuser.md)
- **Install & upgrades**: [USB/optical installer](docs/installer-iso.md), [offline components](docs/installer-components-plan.md), [kernel upgrade](docs/kernel-upgrade.md), [LAN APK feeds](docs/lan-apk-feeds.md), [APK rebuild diagnosis](docs/apk-rebuild-release.md), [LZ4 squashfs](docs/squashfs-lz4.md)
- **Desktop & media**: [GNOME](docs/gnome-desktop.md), [desktop setup](docs/desktop-setup.md), [input methods](docs/desktop-ime.md), [audio](docs/desktop-audio.md), [Google Chrome](docs/google-chrome.md), [Konsole](docs/konsole.md), [hardware & kernel](docs/desktop-kernel.md)
- **Apps, containers & dev**: [Flatpak](docs/flatpak.md), [AppImage](docs/appimage.md), [Podman](docs/podman-rootless.md), [Distrobox](docs/distrobox.md), [libvirt](docs/libvirt.md), [virt-manager](docs/virt-manager.md), [native development](docs/native-development.md), [Qt6 development](docs/qt6-development.md)
- **Routing & ops**: [full cone NAT](docs/fullcone-nat.md), [DNS fast path](docs/dnsmasq-nftset.md), [daed](docs/daed.md), [irqbalance netdev pools](docs/irqbalance-netdev-cpus.md), [uci-history](docs/uci-history.md), [router-audit](docs/router-audit.md), [needrestart](docs/needrestart.md)
- **Sources & release**: [feed repository list](configs/github-source-repositories.json), [GitHub source hosting](docs/github-source-hosting.md), [publication readiness](docs/publication-readiness.md)

Each feature has a matching `docs/*-validation.md` validation record.

## License

Based on [OpenWrt](https://github.com/openwrt/openwrt) and licensed under
GPL-2.0; see [COPYING](COPYING). Each package is distributed under its own
license.
