# USB and optical installer

The optional x86_64 native-systemd installer creates a fresh whole-disk GPT,
installs a clean base router-and-operations squashfs that also runs the live
environment, and installs user-selected optional components offline from a
same-build signed APK repository embedded in the ISO. UEFI and BIOS boot are
supported; UEFI uses the removable boot path without NVRAM changes.

Component catalog and validation:
`configs/installer-components.json`,
[implementation validation](installer-components-implementation-validation.md), and
[KDE Plasma validation](kde-plasma-validation.md).

## Build

Build the componentized installer ISO from the **full desktop profile**
(`configs/x86-64-systemd-desktop.config`) with **Plasma packages enabled** and
**APK signing enabled** (`CONFIG_SIGNED_PACKAGES=y`). Plasma is optional at
installation time. Its APKs must be available at build time so the offline
repository can offer that choice.
`scripts/build-installer-components.py` verifies that the build repository is
signed and contains the complete base router/ops package set plus all ten
optional components defined in `configs/installer-components.json` (`gnome`,
`plasma`, `audio`, `ime`, `rdp`, `sunshine`, `flatpak`, `appimage`,
`virtualization`, `containers`). Pure-router configurations such as
`configs/x86-64-systemd-router.config` do not build those packages and are
rejected, and disabling `CONFIG_SIGNED_PACKAGES` is rejected because the live
installer verifies the offline repository against `/rom/etc/apk/keys`.

Run from the repository root with an existing full-desktop `.config`. In a new
checkout, start with `configs/x86-64-systemd-desktop.config`. Merge the Plasma
APK and installer fragments. The inner `m+` merge preserves existing `=y`
selections, including Plasma if it is already built into the image.

```sh
./scripts/kconfig.pl + m+ .config configs/plasma-packages.config configs/installer-iso.config > .config.new &&
mv .config.new .config &&
make defconfig &&
python3 scripts/build-and-publish.py build-only -j12 V=s
```

The artifact is
`bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-installer.iso`.
The host needs xorriso. No feed publication or router deployment is performed.
The normal combined image still includes the normal local overlay. The installer
rootfs includes only git-tracked `files/` paths from the pristine package tree;
untracked personal settings and accounts are excluded. A source archive without
git uses an empty overlay.

## Start the installer

Write the ISO raw to a USB stick with Etcher, Rufus **DD mode**, or `dd` to the
whole USB device, followed by `sync`. Select the USB device carefully: writing it
erases its contents. For example, replace the output device with the verified USB
stick before running:

```sh
sudo dd if=bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-installer.iso of=/dev/REPLACE_USB bs=4M status=progress conv=fsync
sync
```

The same ISO can also boot from a SATA virtual CD-ROM under BIOS or UEFI.
A small external initramfs locates USB partition 3, or checks the optical image's
MBR signature and maps its appended squashfs read-only through a loop device.
The squashfs payload is stored once. Rufus ISO mode and Ventoy remain unsupported.
The x86_64 installer p3 uses the same plain LZ4 selection as the normal firmware
and is copied unchanged to installed p2; guided ROM sizing follows the actual,
larger payload. See [LZ4 squashfs images](squashfs-lz4.md) for compatibility and
old-rescue-kernel restrictions.

### Testing in virt-manager

Attach this ISO as a **SATA CD-ROM** and put the CD-ROM first in the boot
order, with the writable target disk second. BIOS and UEFI are supported.
Standard VGA and VirtIO video with SPICE OpenGL are validated display paths.
Select the normal installer entry for the graphical console. For VirtIO 3D,
keep 3D acceleration enabled and use a local SPICE connection with a render node
belonging to the host GPU. A minimal graphics/video configuration is:

```xml
<graphics type='spice'>
  <listen type='none'/>
  <image compression='off'/>
  <gl enable='yes' rendernode='/dev/dri/renderD128'/>
</graphics>
<video>
  <model type='virtio' heads='1' primary='yes'>
    <acceleration accel3d='yes'/>
  </model>
</video>
```

The host's SPICE client needs EGL/DMA-BUF support and correct initial-frame
repainting. Keep `<listen type='none'/>` (removing `autoport='yes'` and
`<listen type='address'/>`): in QEMU 11.1+ with SPICE >= 0.15.3, a non-zero
SPICE TCP port sets `spice_remote_client`, routing GL scanouts through a
linear/blit texture path that produced black `(0, 0, 0, 255)` DMA-BUF textures
from SeaBIOS onward on a Fedora 45 / QEMU 11.1.3 / AMD `renderD128` host even
for local `openGraphicsFD` clients. An unpatched host `spice-gtk` may also show
black when opening or reconnecting to an already idle menu until a guest key
triggers a draw. A running guest and QMP `screendump` returning `no surface` do
not prove a failed boot: VirtIO GL can have no CPU surface for QMP to capture.
Check the actual SPICE window and serial console separately. See the
[SPICE client validation](spice-egl-build-validation.md) for the repaint checks.
Replacing a guest ISO does not update the host's SPICE client library.

An offline installer can boot without a network adapter. Missing preinit network
cleanup is nonfatal.
The installer limits console printk output to errors to keep kernel warnings
from overwriting forms; the messages remain available in the kernel log.

Attaching the ISO as a **read-only raw USB disk** also remains supported. For
libvirt, use either `device='cdrom'` with a SATA target, or `device='disk'` with a
USB target. For example (replace the path):

```xml
<disk type='file' device='cdrom'>
  <driver name='qemu' type='raw'/>
  <source file='/absolute/path/openwrt-x86-64-generic-installer.iso'/>
  <target dev='sda' bus='sata'/>
  <readonly/>
  <boot order='1'/>
</disk>
```

Eject or detach the installation media after installation before booting the
installed system. The target disk remains a separate writable virtual disk.

Choose **Install OpenWrt**, or **Install OpenWrt (serial console)** for ttyS0.
The English whiptail interface runs on tty1 or ttyS0. A root shell is available
on tty2; the graphical entry also provides a ttyS0 shell. The live root uses tmpfs
for all live writes. The installer does not start the ordinary router services.

The screens cover target disk, optional components, guided/manual partitioning,
physical ports, LAN, WAN, firewall, accounts, and confirmation. Cancel/Esc moves
back one screen and preserves previous selections. Nine optional components
(`gnome`, `audio`, `ime`, `rdp`, `sunshine`, `flatpak`, `appimage`,
`virtualization`, `containers`) are selected by default, while `plasma` (KDE
Plasma 6.8.3) defaults to unchecked and can be enabled alongside or instead of
`gnome`. Shared desktop add-ons (`audio`, `ime`, `rdp`, `sunshine`, `flatpak`,
`appimage`) require at least one desktop (`gnome` or `plasma`) and pull in
desktop-specific integration packages automatically. Unselected components are
not installed. Missing component dependencies are reported on the selection
screen without silently re-checking unchecked items.
Before erasing the target disk, the installer runs an offline APK preflight
against the embedded signed repository using the booted base system's trusted
keys (`/rom/etc/apk/keys`), verifies package checksums and build identity, and
enforces an overlay minimum covering the actual APK unpacked component size,
overhead, and at least 1 GiB reserve.
Guided partitioning uses ext4 by default; btrfs and xfs are available. Manual mode
edits the **new** layout and optional data partitions, with no preservation of
existing partitions or dual boot. Sizes are whole MiB; one partition can consume
the remaining space. Extra data partitions are formatted but left unmounted.

Choose WAN and LAN ports using MAC, driver and carrier information. The default
LAN is 192.168.1.1/24 with DHCP start 100 and count 150. WAN offers DHCP, PPPoE,
static or none. IPv6 is enabled by default. WAN masquerade and LAN to WAN
forwarding are enabled; full-cone NAT is disabled. Further policy can be changed
later in LuCI.

Root needs a password. An optional regular user can start the selected desktop
automatically; when both `gnome` and `plasma` are selected, the installer lets
you choose the default desktop session (`gnome` or `plasma`).
Passwords are immediately hashed with SHA-512 crypt. The final summary hides
passwords and hashes. Installation requires an explicit, default-No confirmation
that all data on the selected disk will be erased. On errors, return to the
summary or open a shell; details are recorded in `/tmp/openwrt-installer.log`.

## Installed layout and first boot

| Partition | Role | Default |
| --- | --- | --- |
| 128 | BIOS embedding gap | sectors 34–2047 |
| 1 | FAT32 ESP, label kernel | 512 MiB, minimum 64 MiB |
| 2 | Read-only squashfs, name rootfs | at least 1 GiB, scales with payload |
| 3 | Overlay, name/label rootfs_data | remaining space, minimum 2 GiB |
| 4+ | Optional data | manual sizes and filesystems |

Disk GUID ends in `00`; partition N uses that GUID with final byte N. The root
PARTUUID therefore ends in `02`, allowing the normal x86 preinit to mount p1.
`/boot` is the ESP's `boot` subtree and keeps the combined image GRUB layout.
`kernelctl` manages later versioned kernels and retains rescue entries.

The overlay already contains `upper`, `work`, and `.fs_state -> 2`, preserving
installation settings on first boot. Network is written from scratch; stock DHCP
and firewall defaults are edited by UCI. The selected IPv6 policy survives the
stock odhcpd first-boot defaults. The installed GRUB uses the unique FAT
UUID rather than the shared `kernel` label. The failsafe entry uses the new root PARTUUID too.

The firstboot unit runs after OpenWrt defaults create the sudo group. It creates
the optional user, sets `desktop.main.session` via UCI and runs `desktop-setup`
(with `--no-autostart` when boot autostart is disabled) if `gnome` and/or
`plasma` was selected, and runs `desktop-audio-setup` if `audio` was selected.
It deletes the private request only after success; failures remain in the journal
and retry on the next boot. On other systems the request is absent and the unit
is skipped. `/etc/openwrt-installer/install.json` contains a redacted summary.

## Unattended installation and recovery

`openwrt-installer --answers FILE --dry-run` validates and displays a planned
installation (including resolved component packages and space requirements).
`openwrt-installer --answers FILE` executes it, without another confirmation.
In `--answers`, `components` accepts a list of component IDs (`[]` for base
system only; omitting `components` selects all default components). Unknown
component IDs or missing dependencies fail before any disk writes. Both require
the live installer entry and exclude the source media and read-only disks. Only
`$6$` password hashes are accepted; protect answers files with mode 0600 because
PPPoE credentials remain plaintext as required by UCI.

Example answers JSON:

```json
{
  "disk": "/dev/nvme0n1",
  "components": ["gnome", "audio", "ime", "rdp", "sunshine", "flatpak", "appimage", "virtualization", "containers"],
  "partitions": [
    {"role": "boot", "size_mib": 512},
    {"role": "rom", "size_mib": 1024},
    {"role": "overlay", "fs": "ext4", "size_mib": null},
    {"role": "data", "fs": "xfs", "size_mib": 20480}
  ],
  "network": {
    "wan_port": "eth1",
    "lan_ports": ["eth0", "eth2"],
    "lan": {"ipaddr": "192.168.1.1", "netmask": "255.255.255.0",
            "dhcp": true, "start": 100, "limit": 150},
    "wan": {"proto": "dhcp"},
    "ipv6": true
  },
  "firewall": {"masq": true, "fullcone": false, "lan_to_wan": true},
  "accounts": {
    "root_password_hash": "$6$...",
    "user": {
      "name": "alice",
      "password_hash": "$6$...",
      "desktop_session": "gnome",
      "desktop_autostart": true
    }
  }
}
```

Per-protocol `wan` fields: PPPoE `{"proto":"pppoe","username":...,"password":...}`;
static `{"proto":"static","ipaddr":...,"netmask":...,"gateway":...,"dns":[...]}`;
or `{"proto":"none"}`. In `partitions`, `size_mib: null` consumes the remaining
disk space. Under `accounts.user`, `desktop_session` selects `"gnome"` or
`"plasma"`, and `desktop_autostart` controls boot autostart (`gnome_autostart`
is still accepted as a backward-compatible alias).

After success remove the USB or eject the virtual CD-ROM, then reboot. The target disk contains its own BIOS
and UEFI boot files, kernel, root filesystem and overlay, so later boots do not
need the USB. For installation trouble use the tty2
shell and log. For an installed system use the native OpenWrt failsafe entry in GRUB. This installer erases the target immediately after confirmation; an
interrupted install can be restarted from the USB.

Validation results and remaining acceptance gaps are recorded in
[installer-iso-validation.md](installer-iso-validation.md).
