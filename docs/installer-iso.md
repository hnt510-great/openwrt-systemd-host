# USB and optical installer

The optional x86_64 native-systemd installer creates a fresh whole-disk GPT and
installs the same clean squashfs that runs the live environment. UEFI and BIOS
boot are supported; UEFI uses the removable boot path without NVRAM changes.

## Build

Preserve the current configuration, merge `configs/installer-iso.config`, then
normalize it:

```sh
./scripts/kconfig.pl + .config configs/installer-iso.config > .config.new
mv .config.new .config
make defconfig
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

### Testing in virt-manager

Attach this ISO as a **SATA CD-ROM** and put the CD-ROM first in the boot
order, with the writable target disk second. BIOS and UEFI are supported.
Standard VGA is the validated display model for the installer console. Select
the normal installer entry for the graphical console.

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

The screens cover target disk, guided/manual partitioning, physical ports, LAN,
WAN, firewall, accounts, and confirmation. Cancel/Esc moves back one screen.
Guided partitioning uses ext4 by default; btrfs and xfs are available. Manual mode
edits the **new** layout and optional data partitions, with no preservation of
existing partitions or dual boot. Sizes are whole MiB; one partition can consume
the remaining space. Extra data partitions are formatted but left unmounted.

Choose WAN and LAN ports using MAC, driver and carrier information. The default
LAN is 192.168.1.1/24 with DHCP start 100 and count 150. WAN offers DHCP, PPPoE,
static or none. IPv6 is enabled by default. WAN masquerade and LAN to WAN
forwarding are enabled; full-cone NAT is disabled. Further policy can be changed
later in LuCI.

Root needs a password. An optional regular user can start GNOME automatically.
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
UUID rather than the shared `kernel` label. Recovery and failsafe entries use the
new root PARTUUID too.

The firstboot unit runs after OpenWrt defaults create the sudo group. It creates
the optional user and invokes `desktop-setup` under the running systemd instance.
It deletes the private request only after success; failures remain in the journal
and retry on the next boot. On other systems the request is absent and the unit
is skipped. `/etc/openwrt-installer/install.json` contains a redacted summary.

## Unattended installation and recovery

`openwrt-installer --answers FILE --dry-run` validates and displays a planned
installation. `openwrt-installer --answers FILE` executes it, without another
confirmation. Both require the live installer entry and exclude the source media
and read-only disks. Answers follow the schema and example in
[installer-iso-plan.md](installer-iso-plan.md); only `$6$` password hashes are
accepted. Protect answers files with mode 0600 because PPPoE credentials remain
plaintext as required by UCI.

After success remove the USB or eject the virtual CD-ROM, then reboot. The target disk contains its own BIOS
and UEFI boot files, kernel, root filesystem and overlay, so later boots do not
need the USB. For installation trouble use the tty2
shell and log. For an installed system use the GRUB procd recovery or failsafe
entry. This installer erases the target immediately after confirmation; an
interrupted install can be restarted from the USB.

Validation results and remaining acceptance gaps are recorded in
[installer-iso-validation.md](installer-iso-validation.md).
