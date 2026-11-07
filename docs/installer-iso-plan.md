# Plan: x86 installer ISO with a Debian-style TUI

Status: implemented and VM-validated 2026-11-07. The guide is
`docs/installer-iso.md`; build, matrix and regression results are recorded in
`docs/installer-iso-validation.md`. This document retains the approved design and
the research findings behind it, with code references. Physical hardware acceptance
remains separate.

## Optical compatibility amendment — 2026-11-07

Implemented and VM-validated with sequence 54; see the optical compatibility
section in `docs/installer-iso-validation.md`. The user subsequently authorized
adding virtual-CD compatibility. This supersedes
this document's original USB-only/no-initramfs decisions below. Keep the single
appended squashfs payload and existing USB p3 root. Add an external installer
bootstrap that resolves the USB PARTUUID normally, or identifies optical media
by MBR signature and maps the p3 byte range read-only through a loop device.
The installed system and its kernelctl boot flow stay as before. The installer
must identify the optical loop's source and mount the whole CD's ISO9660 for
its manifest/ESP. Validate both BIOS/UEFI SATA CD-ROM installation and USB
regressions, with the installation medium absent on the installed boot.

## Context

The native-systemd x86 firmware currently ships only as
`bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz`. Users
must `dd` it over a whole disk, which gives a fixed layout: a 128 MiB FAT ESP, an 8 GiB root
partition holding the squashfs, and a small internal F2FS overlay in the space after the
squashfs. That is unfriendly on x86 PCs.

The goal is a mainstream-distribution flow:

1. the build emits a hybrid `installer.iso`;
2. written raw to a USB stick, it boots into an installer TUI that looks like Debian's newt
   frontend;
3. the TUI partitions a disk, assigns ports and sets up LAN, WAN, firewall and accounts;
4. the installed system boots into GNOME with working LAN.

The original request (user's own design) had eight steps:

1. **Interface style:** like Debian's TUI.
2. **Disk partitioning:** `boot`, `rom` and `overlayfs` partitions. Select the target drive,
   adjust partition types and sizes, format, create and delete partitions. The overlay supports
   ext4, btrfs and xfs.
3. **Network interface assignment:** identify physical ports, choose WAN and LAN.
4. **LAN:** gateway IP, subnet mask, DHCP pool.
5. **WAN:** PPPoE, DHCP, static IP, IPv6.
6. **Firewall:** WAN/LAN zones, NAT, forwarding policy.
7. **Accounts:** root password, regular user, GNOME auto-start.
8. **Confirmation:** show all settings, then install.

The UI must not be overly complex or list every option. The primary goal is a quick install that
boots into GNOME with LAN connectivity; everything else is left for later. **Avoid over-design and
over-validation.**

## Decisions already made with the user

- **The ISO uses a separate, clean rootfs.** The normal image bakes in the *unversioned*
  personal `files/` overlay; the ISO must not:
  - the `example-user` account and its password hash in `files/etc/uci-defaults/99-zz-example-user`;
  - `99-zzz-local-settings`, which sets desktop, luci, uhttpd, upnpd and attendedsysupgrade;
  - the personal `etc/config/{network,dhcp,firewall,passwall,ddns-go,wgserver,…}`.

  Interpretation (please keep): "clean" means *only the 11 git-tracked files under `files/`*.
  They are non-personal fork defaults: multiuser/sudo group, sudoers, sshd access, uhttpd/LuCI,
  zsh, fstab. See the `CLAUDE.md` gotcha on `files/`. Switching to "no overlay at all" would be a
  one-line change.
- **UEFI and legacy BIOS (CSM)** are both supported, for the ISO and for the installed disk.
- **The installer always takes the whole target disk** and writes a fresh GPT. The manual editor
  edits only the new layout: sizes, filesystems, extra partitions. Keeping foreign partitions or
  dual-boot is out of scope.
- **Sysupgrade is disabled in native systemd mode** (user statement). Sysupgrade layout
  compatibility is therefore *not* a constraint. Ignore `legacy_sdcard_upgrade_mode` and the
  partition-table comparison.
- **English only.** The Linux VT/fbcon cannot render CJK glyphs. Debian needs bterm/fbterm for
  that.
- **Default overlay filesystem:** ext4. fstools supports it natively; btrfs and xfs need the
  fstools patch below.

## Architecture overview

```
installer.iso   (xorriso hybrid; MBR partition table; MBR disk signature S)
  p1  ISO9660  /boot/vmlinuz, /boot/grub/grub.cfg (installer menu),
               /install/esp/ (target ESP tree), /install/manifest.json
  p2  ESP      FAT image, MBR type 0xef: installer GRUB EFI + stub grub.cfg that
               searches the ISO9660 fs by fs-uuid and configfiles its grub.cfg
  p3  squashfs the CLEAN root.squashfs = live installer root AND the exact payload
               dd'd to the target rom partition (Linux type 0x83)
  BIOS: El Torito i386-pc-eltorito core + boot_hybrid.img MBR (--grub2-boot-info)
  UEFI: El Torito EFI entry -> appended partition 2

Live kernel cmdline:
  root=PARTUUID=S-03 rootfstype=squashfs rootwait noinitrd
  openwrt.init=systemd systemd.unit=openwrt-installer.target
  fstools_overlay=tmpfs openwrt.installer=1  <GRUB_CONSOLE_CMDLINE>

Target disk (fresh GPT, ptgen GUID scheme: disk GUID G..00, partition N -> G..0N,
             BIOS-boot p128 -> G..80)
  p128 BIOS boot  sectors 34-2047, always created (for grub-bios-setup)
  p1   boot     FAT32, fs label "kernel", default 512 MiB; same tree as combined-efi's ESP
  p2   rom      raw squashfs; default max(1 GiB, roundup(1.25 x squashfs, 256 MiB)); min = squashfs
  p3   overlay  ext4 (default) | btrfs | xfs; GPT PARTNAME + fs label "rootfs_data"; rest of disk
  p4+  optional extra data partitions (manual mode): formatted, not mounted
Installed GRUB: root=PARTUUID=G..02
```

The clean squashfs is about 730 MB today, so the ISO is about 750 MB. The current
`build_dir/target-x86_64_glibc/linux-x86_64/root.squashfs` is 729,476,459 bytes.

---

## Research findings (read before implementing)

### Existing image machinery

- `target/linux/x86/image/Makefile` already has:
  - `Build/iso` (lines 118–135), an upstream *LiveCD* that puts the whole `TARGET_DIR` into
    ISO9660 with `root=/dev/sr0`. It is optical-only, uncompressed and uses host `mkisofs`
    (absent on this host). **Do not reuse it** for the installer; keep it untouched.
  - `Build/combined` (lines 44–60) builds the ESP tree in `$@.boot` and calls
    `scripts/gen_image_generic.sh`:
    - `$(KDIR)/$(KERNEL_NAME)` → `boot/vmlinuz`;
    - `STAGING_DIR_ROOT/boot/.` (microcode etc.);
    - `grub2/boot.img`;
    - `grub2/gpt-core.img` → `boot/grub/core.img`;
    - `grub2/bootx64.efi` → `efi/boot/`.
  - `Build/grub-config efi` (lines 62–76) renders `grub-efi.cfg` into `$@.boot/boot/grub/grub.cfg`
    with `@GPT_ROOTPART@`. Under systemd it also inserts a "procd recovery" entry (line 75).
  - `Build/onie-installer` (lines 91–116) is a useful example of an installer artifact recipe.
  - `ARTIFACT/...` entries plus `ARTIFACTS-$$(CONFIG_…)` (lines 139–184) show how to add an
    optional artifact.
- `target/linux/x86/image/grub-efi.cfg` uses `search -l kernel -s root` (by FAT label) and
  `@GPT_ROOTPART@`.
- `IMG_PART_SIGNATURE` and `IMG_PART_DISKGUID` come from `include/image.mk:52-55`. The disk GUID
  ends in `00`. `GPT_ROOTPART` = `PARTUUID=<diskguid with 00→02>` (`Makefile:29-30`).
- `scripts/gen_image_generic.sh`:
  - the ESP is `mkfs.fat --invariant -n kernel`;
  - partitions come from `ptgen` (`build_dir/host/firmware-utils-*/src/ptgen.c`);
  - partition GUID = disk GUID + (index+1) on the last byte (ptgen.c:466-467);
  - the BIOS-boot stub is partition 128 in the gap before p1, with GUID + 128 (ptgen.c:500-505);
  - no GPT partition names are set.
- Current config (`.config`): `TARGET_ROOTFS_SQUASHFS=y`, `GRUB_EFI_IMAGES=y`,
  `GRUB_IMAGES` unset, `TARGET_KERNEL_PARTSIZE=128`, `TARGET_ROOTFS_PARTSIZE=8192`,
  `TARGET_IMAGES_GZIP=y`, `GRUB_TIMEOUT="2"`, `TARGET_SERIAL="ttyS0"`, `GRUB_CONSOLE=y`,
  `ISO_IMAGES` unset.
- `config/Config-images.in:289` has `ISO_IMAGES`. Add `INSTALLER_ISO_IMAGES` next to it. The
  `VDI_IMAGES` option shows `select PACKAGE_…` from an image option.

### Clean rootfs: where to branch off

- `package/Makefile:151-166` (`apk_install_rootfs`) installs packages into `TARGET_DIR`, then
  `$(CP) $(TARGET_DIR) $(TARGET_DIR_ORIG)`. **`TARGET_DIR_ORIG` is the pristine package-installed
  tree before `files/`.** After that, `prepare_rootfs` runs with `$(TOPDIR)/files`.
  - It is cached in `ROOTFS_CACHE` (`root` and `root.orig`); both are restored on cache hit.
- `include/rootfs.mk:71-129` (`prepare_rootfs DIR,FILESDIR`):
  - copies FILESDIR only if `$(2)` is non-empty;
  - runs `merge-usr.py --aliases`, the APK post-install scripts and init-script enables;
  - removes `/boot` and `/tmp/*`, then mklibs and the `SOURCE_DATE_EPOCH` touch.
- **Precedent:** `include/image.mk:380-403` (`target-dir-%`) builds per-device variant rootfs
  dirs exactly this way:
  ```
  rm -rf DIR; $(CP) $(TARGET_DIR_ORIG) DIR; [apk add/del]; $(call prepare_rootfs,DIR,$(TOPDIR)/files)
  ```
  The installer's clean rootfs follows the same pattern with a tracked-only files dir.
- Squashfs options: `include/image.mk:274-279`
  (`mksquashfs4 DIR $@ -nopad -noappend -root-owned -comp $(SQUASHFSCOMP) $(SQUASHFSOPT)`).
- Nothing else mutates `TARGET_DIR` between `package/install` and image generation. The only hits
  were initramfs code in `include/kernel-defaults.mk`, which isn't used here.
- Tracked files (`git ls-files files`):
  - `etc/config/fstab`, `etc/skel/.zshrc`, `etc/ssh/sshd_config.d/00-openwrt-access.conf`,
    `etc/sudoers.d/10-multiuser`;
  - `etc/uci-defaults/{99-multiuser,99-openssh-access,99-uhttpd-luci,99-zsh-default}`;
  - `etc/zsh/zshrc`, `lib/upgrade/keep.d/{multiuser,openssh-access}`.
  - `99-multiuser` creates the `sudo` group (`groupadd -r sudo`), and the regular user needs it.

### Kernel: no initramfs is needed for the live USB boot

These are built in (`=y`) in `target/linux/x86/{64/,}config-7.3` plus
`target/linux/generic/config-7.3`:
`USB`, `USB_XHCI_HCD`, `USB_XHCI_PCI`, `USB_EHCI_HCD`, `USB_STORAGE`, `SCSI`, `BLK_DEV_SD`,
`ATA`, `SATA_AHCI`, `BLK_DEV_NVME`, `VIRTIO_BLK`, `SQUASHFS(+XZ)`, `ISO9660_FS`, `EXT4_FS`,
`F2FS_FS`, `OVERLAY_FS`, `BLK_DEV_LOOP`, `EFI_PARTITION`, `MSDOS_PARTITION`, `DRM_SIMPLEDRM`,
`SYSFB_SIMPLEFB`, `FRAMEBUFFER_CONSOLE`, `HID_GENERIC`, `USB_HID`.

So `root=PARTUUID=S-03 rootfstype=squashfs noinitrd` mounts the squashfs straight from the
stick.

btrfs and xfs are modules (`kmod-fs-btrfs`, `kmod-fs-xfs`), both `AutoLoad,30,…,1`, i.e. boot
modules (`package/kernel/linux/modules/fs.mk:72,641`). Preinit loads them before `mount_root`.
For newer kernels from APK, kernelctl builds `/boot/kernels/<rel>/initramfs.gz` from the
`/etc/modules-boot.d` rules (`docs/kernel-upgrade.md` around line 104). That means a btrfs or xfs
overlay can still be mounted with a kernel whose modules live in the overlay. **Verify this**,
because the physical router only exercises ext4 extroot.

### fstools: how the overlay is chosen today

Source: `build_dir/target-x86_64_glibc/fstools-2026.10.18~907cf449/`, recipe
`package/system/fstools/` (`PKG_RELEASE:=2`). The existing local patch is
`patches/001-disable-xino-for-squashfs-root.patch`.

- `mount_root.c` `start()` (lines 34–100):
  - `data = volume_find(dataname)`, where dataname is `rootfs_data` or `fstools_overlay_name=`.
  - Then `mount_extroot("")` reads the *rom's* `/etc/config/fstab`.
  - Then the switch on `volume_identify(data)`: `FS_NONE` or `FS_DEADCODE` → `ramoverlay()`;
    `FS_EXT4`, `FS_F2FS`, `FS_JFFS2` or `FS_UBIFS` → `mount_overlay()`.
- `libfstools/volume.c:24-35` keeps drivers sorted by **descending** priority: fit 30, partname 25,
  ubi 20, mtd 10, rootdisk 0 (unset). `volume_find` returns the first hit, so **partname wins
  over rootdisk**.
- `libfstools/rootdisk.c:160-197` matches only `"rootfs_data"`. It finds the root device via
  `get_rootdev("/")` or `"/rom"` and places a loop overlay at the squashfs end, aligned to
  64 KiB. That is today's internal F2FS overlay.
- `libfstools/partname.c:79-150` has a **blocker**:
  - with `root=` not starting with `/` (we use `PARTUUID=`), it returns NULL unless
    `fstools_partname_fallback_scan=1`, which scans *every* disk;
  - with `root=/dev/...` it scans only that disk.
  - It matches `PARTNAME=` from `/sys/class/block/*/uevent`.
  - `partname_volume_init` calls `block_volume_format(v, 0, parent)`.
- `libfstools/common.c:89-126` (`block_file_identify`) knows only gzip (TARGZ), deadc0de, F2FS
  (`0xF2F52010` at 0x400) and ext4 (`0xEF53` at 0x438). Everything else is `FS_NONE`.
- `common.c:162-230` (`block_volume_format`): `FS_NONE` → **mkfs.f2fs or mkfs.ext4 the
  volume**. **A btrfs or xfs `rootfs_data` partition would be silently reformatted today.**
- `libfstools/overlay.c`:
  - `overlay_fs_name()` (around line 272) maps ext4, f2fs and ubifs; the default is "jffs2".
  - `jffs2_switch` switch at lines 330–360.
  - `mount_overlay` (around line 440): after mounting, `mount_extroot(overlay_mp)` checks the
    overlay's own fstab for extroot. This is how the physical router's NVMe extroot works.
  - Then the `fs_state` switch (around line 468): `FS_STATE_UNKNOWN` → set PENDING → **falls
    through to `overlay_delete(overlay_mp, true)`**, which wipes the overlay contents.
  - **So a pre-populated overlay needs `.fs_state` → `2` (`FS_STATE_READY`).** The enum in
    `libfstools/libfstools.h:36-38` is UNKNOWN=0, PENDING=1, READY=2. `fs_state_get` reads the
    symlink `<dir>/.fs_state` (`overlay.c:400-440`).
- `block.c` `mount_extroot()` (around line 2026) only allows ext*, f2fs, btrfs, ntfs and ubifs, so
  **xfs extroot is rejected**. `check_extroot` UUID pinning applies only if
  `/etc/.extroot-default` exists. We don't use extroot. This is why the design uses partname
  rather than extroot.
- `block.c:627` skips automount for partitions named `rootfs` or `rootfs_data`.
- `factoryreset.c:139` and `snapshot.c` hard-code `volume_find("rootfs_data")`. Using the standard
  name `rootfs_data` for p3 keeps them pointed at the real overlay.
- Cmdline knobs that already exist: `fstools_overlay_name`, `fstools_ignore_partname`,
  `fstools_partname_fallback_scan`, `fstools_overlay_fstype` (f2fs/ext4/auto for mkfs only) and
  `fstools_overlay_compression_type`.
- `libfstools/volume.h:67-79`: `volume_init()` and `volume_identify()` are NULL-safe and return
  -1. A missing data volume plus no extroot leaves `/` read-only with no overlay. That is why an
  explicit tmpfs knob is needed for the live installer.

### Preinit, /boot mount and kernelctl

- `package/base-files/files/lib/preinit/80_mount_root`: `do_mount_root` runs
  `mount_root start`, then `boot_run_hook preinit_mount_root`, then the `sysupgrade.tgz` restore.
- `target/linux/x86/base-files/lib/preinit/20_check_iso` ramoverlays when `/dev/root` is iso9660
  (upstream LiveCD).
- `target/linux/x86/base-files/lib/preinit/79_move_config` runs `export_bootdevice` plus
  `export_partdevice partdev 1`. It mounts **partition 1** of the root disk at `/boot`, moves
  `sysupgrade.tgz`, then `mount --bind /boot/boot /boot`.
- `package/base-files/files/lib/upgrade/common.sh:168-218` (`export_bootdevice`):
  - for `root=PARTUUID=<guid ending 02>` (or `…0?/PARTNROFF=1`) it compares the GPT **disk
    GUID** at byte 568 with the root PARTUUID with `0?`→`00`;
  - for the MBR form `PARTUUID=ssssssss-NN` it compares the MBR signature at byte 440.
  - **Therefore the target disk must follow the ptgen scheme:** disk GUID `G..00`, root (p2)
    PARTUUID `G..02`, boot = partition 1.
  - On the ISO, `root=PARTUUID=S-03` matches the stick via its MBR signature, so `79_move_config`
    would try to mount the stick's p1 (ISO9660) as `/boot`. Skip it in installer mode.
- `package/custom/openwrt-kernel-upgrade/files/kernelctl`:
  - `boot_mount()` (line 244) requires `/boot` to be a rw vfat or ext4 bind of the boot
    partition's `/boot` subdir;
  - `bootargs()` (line 265) copies `/proc/cmdline` minus `BOOT_IMAGE`, `openwrt.init`,
    `failsafe`, `firmware_class.path`, `noinitrd` and `quiet`, and requires a `root=` argument;
  - `dispatcher()` (line 299) rewrites `grub.cfg` with `search --fs-uuid --set=root <vfat uuid>`
    and keeps `grub.cfg.rescue`;
  - per-kernel entries go to `boot/grub/openwrt.cfg`.
  - So the installer only needs to produce a combined-style ESP; kernelctl takes over as on a
    combined-image install.
- `target/linux/x86/base-files/lib/upgrade/platform.sh`:
  - `platform_do_bootloader_upgrade` (around line 121) is the exact BIOS GRUB install recipe:
    ```
    echo "(hd0) /dev/$diskdev" > device.map
    grub-bios-setup -m device.map -d <ESP>/boot/grub -r hd0,gpt1 /dev/$diskdev
    ```
  - `platform_legacy_sdcard_post_upgrade` (around line 140) shows the `grub.cfg` PARTUUID
    rewrite (`sed "s/\(PARTUUID=\)[a-f0-9-]\+/\1<uuid>/ig"`) and reads the p2 GUID at offset
    1168.
- `package/system/procd/patches/100-systemd-compatibility.patch`:
  `openwrt_systemd_requested()` is true when the cmdline has `openwrt.init=systemd` and no
  failsafe. systemd reads `systemd.unit=` from `/proc/cmdline` itself, so
  `systemd.unit=openwrt-installer.target` should just work. **Verify in the boot spike.**

### GRUB packaging

- `package/boot/grub2/Makefile:124-176`:
  - `Package/grub2/install` copies `boot.img` and `cdboot.img` to `STAGING_DIR_IMAGE/grub2`, and
    builds `gpt-core.img`, `generic-core.img`, `eltorito.img` (as `-O i386-pc`, concatenated
    with `cdboot.img` by `Build/iso`) and `legacy-core.img`;
  - `Package/grub2-efi/install` builds `bootx64.efi` and `iso-bootx64.efi`.
  - All use `-p /boot/grub`. The embedded early config `files/grub-early.cfg` is
    `configfile (hd0,msdos1)/boot/grub/grub.cfg`, `sed`-ed to `gpt1` for gpt/efi images.
  - `iso-bootx64.efi` has no `search` module and its early config hard-codes `(hd0,msdos1)`.
    **Not suitable for USB.** Build dedicated installer images instead:
    - `installer-eltorito.img` with `-O i386-pc-eltorito`, like `grub-mkrescue`;
    - `installer-bootx64.efi`;
    - copy `grub-core/boot_hybrid.img`.
  - With `CONFIG_OPENWRT_KERNEL_UPGRADE`, the packages also ship modules to
    `/usr/share/openwrt-kernel/grub/{i386-pc,x86_64-efi}`.
- Host tools: `/usr/bin/xorriso` exists (Debian host). `mkisofs` and `genisoimage` are absent.
  `include/prereq-build.mk` has no xorriso check, so fail inside the recipe with a clear message
  (or add a check). `mkfs.fat`, `mcopy` and `mmd` come from `tools/dosfstools` and `tools/mtools`.
  Host `mksquashfs` is absent; use `$(STAGING_DIR_HOST)/bin/mksquashfs4`.

### Target userspace already available (relevant `.config` selections)

| Area | Already selected |
| --- | --- |
| Partitioning | `sfdisk`, `fdisk`, `parted`, `partx-utils`, `lsblk`, `blkid`, `losetup` |
| Filesystems | `e2fsprogs`, `dosfstools`, `xfs-mkfs`, `mkf2fs` |
| Boot | `grub2`, `grub2-efi`, `grub2-bios-setup`, `grub2-editenv` |
| Runtime | `python3` / `python3-light`, `ucode`, `lua`, `openssl-util` |
| Accounts | shadow `useradd`, `usermod`, `groupadd`, `chpasswd`, `passwd` |
| WAN/IPv6 | `ppp`, `ppp-mod-pppoe`, `odhcp6c` |
| Kernel modules | `kmod-usb-storage(-uas)`, `kmod-scsi-cdrom` |

**Not selected:** `btrfs-progs` (needed for `mkfs.btrfs`) and `whiptail`. whiptail is in
`feeds/packages/libs/newt/Makefile`, package `whiptail`, `DEPENDS:=+libnewt +libpopt +libslang2`.
The default newt palette (blue root, grey windows) *is* the Debian installer look.

### Desktop and accounts

- `package/custom/openwrt-desktop/files/desktop-setup USER`:
  - requires `/run/systemd/system` (running systemd) and uses `systemd-run --wait` with a PAM
    session, so **it cannot run from uci-defaults or at install time**;
  - adds the user to `video` and `render`, creates the keyring bootstrap secret
    (`openssl rand`), runs `desktop-user-setup` as the user;
  - sets `uci desktop.main.user`/`enabled=1`, then `/etc/init.d/desktop enable`/`restart`;
  - for a fresh user (no existing keyring) it does not prompt.
- `/usr/libexec/login.sh` and `openwrt-console@.service`
  (`package/system/systemd-openwrt/files/openwrt-console@.service`, `askfirst`) give a root
  shell when root has no password. The clean live rootfs root has none. Use it for the
  tty2/ttyS0 shells in the installer target.
- systemd unit packaging pattern (`package/custom/openwrt-kernel-upgrade/Makefile:31-36`): install
  to `/usr/lib/systemd/system/` and `$(LN)` into `/etc/systemd/system/multi-user.target.wants/`.

### Networking defaults

- `target/linux/x86/base-files/etc/board.d/02_network`: the generic x86 default is LAN `eth0`,
  WAN `eth1`.
- `/etc/init.d/boot` (`package/base-files/files/etc/init.d/boot:7,68`): `config_generate` (only
  missing configs), then `uci_apply_defaults` in `ls` order.
- No systemd net-naming policy (`NamePolicy`, `80-net-setup-link`) is configured in this tree, so
  NICs keep kernel `eth*` names. The live installer uses the same kernel and udev as the
  installed system, so the names match. Verify on the VM.
- Clean rootfs: `/etc/config/network` is generated at first boot unless the installer writes one;
  `dhcp` (from `package/network/services/dnsmasq/files/dhcp.conf`) and `firewall` (from the
  firewall4 package) are stock.
- Full cone (`docs/fullcone-nat.md`): `firewall.@defaults[0].fullcone='2'`.

### Registry and conventions

- `configs/custom-package-updates.json` is `{"schema", "packages": {name: {...}}}`. A local
  package entry looks like
  `"cockpit-runtime-deps": {"provider": "local", "reason": "Locally maintained integration package"}`.
  The updater fails on unregistered packages.
- Host tests load package Python with
  `importlib.machinery.SourceFileLoader` (`scripts/tests/test-kernel-upgrade.py:25-28`).
- VM helpers: `scripts/test-image-network.py` boots an exact image as a router+client KVM pair
  under UEFI. `scripts/tests/test-daed-vm.py` reuses it.
- Memory/user rule: describe each major feature in
  `package/base-files/system-description.systemd.md` and bump base-files `PKG_RELEASE`, with no
  dated changelog.
- Use full builds through `python3 scripts/build-and-publish.py build-only -j12 V=s` (it reserves
  a kernel build number). Never publish or touch the physical router without explicit
  authorization.

---

## Implementation plan

### 1. fstools: overlay on a separate partition

Add `package/system/fstools/patches/002-overlay-partition.patch` (quilt: `make
package/system/fstools/refresh`) and bump `PKG_RELEASE` 2→3.

1. **`libfstools/partname.c`.** When `root=` is present but not a `/dev/` path and fallback is
   not requested, resolve the disk that holds the mounted root:
   - `stat("/")`; if `/` is an overlay (anonymous dev), use `stat("/rom")`;
   - then `/sys/dev/block/<maj>:<min>`, realpath; if a `partition` file exists, the parent
     directory is the disk.
   - Glob only `/sys/class/block/<disk>/*/uevent`.

   Keep the existing `/dev/` and fallback branches. A non-block or unresolvable root returns NULL
   as today.
2. **`libfstools/libfstools.h` and `common.c`.** Add `FS_BTRFS` (8-byte magic `_BHRfS_M` at
   offset 0x10040) and `FS_XFS` (`XFSB` big-endian at offset 0), detected before returning
   `FS_NONE`. Note: the first `fread` at offset 0 is not length-checked today; check `n`.
   Recognised types are never formatted.
3. **`libfstools/overlay.c`.** `overlay_fs_name()` maps btrfs and xfs, and the `jffs2_switch`
   and `mount_overlay` switch arms include them next to `FS_EXT4`.
4. **`mount_root.c`.**
   - `start()` and `done()` handle `FS_BTRFS`/`FS_XFS` like `FS_EXT4`.
   - New knob `fstools_overlay=tmpfs`: `start()` returns `ramoverlay()` immediately, and
     `done()` returns 0.

Expected effect on existing systems: none. Combined images have no `rootfs_data` partition name,
and the physical router's rom fstools never changes because sysupgrade is disabled. It only gets
the APK fstools for runtime tools.

### 2. Boot pieces

- **`package/boot/grub2/Makefile`** (staging only):
  - copy `$(PKG_BUILD_DIR)/grub-core/boot_hybrid.img`;
  - build `installer-eltorito.img`:
    `grub-mkimage -O i386-pc-eltorito -p /boot/grub` with modules
    `biosdisk iso9660 part_msdos part_gpt configfile linux normal search search_fs_uuid search_fs_file serial terminal test echo boot ls reboot vga at_keyboard`;
  - build `installer-bootx64.efi`:
    `-O x86_64-efi -p /boot/grub`, modules
    `fat iso9660 part_msdos part_gpt configfile linux normal search search_fs_uuid search_fs_file serial terminal test echo boot ls reboot efi_gop efi_uga at_keyboard`.
  - No embedded config. GRUB then uses the device it booted from plus `/boot/grub`.
  - Bump `PKG_RELEASE` only if an APK payload changes.
- **`target/linux/x86/base-files/lib/preinit/79_move_config`:** `grep -q 'openwrt.installer=1'
  /proc/cmdline && return 0` at the start of `move_config`.
- **New `target/linux/x86/image/grub-installer.cfg`.** It uses `@SERIAL_CONFIG@`,
  `@TERMINAL_CONFIG@`, `@TIMEOUT@` and `@TITLE@`, plus a new `@INSTALLER_ROOT@`
  (`root=PARTUUID=S-03`). Entries:
  - "Install OpenWrt": the live cmdline above with `systemd.unit=openwrt-installer.target`;
  - "Install OpenWrt (serial console)": `systemd.unit=openwrt-installer-serial.target`.

### 3. Image recipe: clean rootfs + hybrid ISO

- **`config/Config-images.in`:** `config INSTALLER_ISO_IMAGES`, "Build installer ISO (USB,
  UEFI + BIOS)".
  - `depends on TARGET_x86 && GRUB_EFI_IMAGES && TARGET_ROOTFS_SQUASHFS && OPENWRT_SYSTEMD`;
  - `select PACKAGE_openwrt-installer`.
- **`target/linux/x86/image/Makefile`:**
  - Factor lines 45–53 of `Build/combined` (the ESP file copy) into a shared macro, e.g.
    `Build/efi-boot-files`, used by `combined` and `installer-iso`. **Check that
    `combined-efi.img` is byte-identical before and after the refactor.**
  - `ARTIFACT/installer.iso := grub-config efi | installer-iso`, plus
    `ARTIFACTS-$$(CONFIG_INSTALLER_ISO_IMAGES) += installer.iso`.
  - `Build/installer-iso`:
    1. **Clean rootfs:**
       - `rm -rf $@.root $@.files; $(CP) $(TARGET_DIR_ORIG) $@.root`;
       - `git -C $(TOPDIR) ls-files -z files | (cd $(TOPDIR) && tar --null -T - -cf -) | tar -C $@.files -xf -`
         (fall back to an empty dir without git);
       - `$(call prepare_rootfs,$@.root,$@.files/files)`;
       - `mksquashfs4 $@.root $@.squashfs -nopad -noappend -root-owned -comp $(SQUASHFSCOMP) $(SQUASHFSOPT)`;
       - remove `$@.root`.
    2. **ISO tree `$@.iso/`:**
       - `boot/vmlinuz` (`$(KDIR)/$(KERNEL_NAME)`);
       - `boot/grub/grub.cfg` (rendered `grub-installer.cfg`);
       - `install/esp/` = `$@.boot` (output of `grub-config efi`) plus the shared ESP files;
       - `install/manifest.json`: version, kernel release, squashfs byte size and SHA-256,
         and the literal `$(GPT_ROOTPART)` string the installer replaces.
    3. **`$@.esp.img`** (FAT; `mkfs.fat -C … -S 512`; `mmd`/`mcopy`):
       - `efi/boot/bootx64.efi` = `installer-bootx64.efi`;
       - `boot/grub/grub.cfg` = `search --no-floppy --fs-uuid --set=root <ISO uuid>`,
         `set prefix=($root)/boot/grub`, `configfile $prefix/grub.cfg`.
       - GRUB's ISO9660 "uuid" is the volume modification date. Set it deterministically with
         xorriso `--modification-date=YYYYMMDDhhmmsscc` from `SOURCE_DATE_EPOCH`.
    4. **xorriso** (fail clearly if `command -v xorriso` fails):
       ```
       xorriso -as mkisofs -R -J -V OPENWRT_INSTALL --modification-date=<d> -o $@ \
         --grub2-mbr $(STAGING_DIR_IMAGE)/grub2/boot_hybrid.img -partition_offset 16 \
         --mbr-force-bootable \
         -append_partition 2 0xef $@.esp.img -append_partition 3 0x83 $@.squashfs \
         -c boot/boot.cat \
         -b boot/grub/bios.img -no-emul-boot -boot-load-size 4 -boot-info-table --grub2-boot-info \
         -eltorito-alt-boot -e --interval:appended_partition_2:all:: -no-emul-boot \
         $@.iso
       ```
       Copy `installer-eltorito.img` to `$@.iso/boot/grub/bios.img` first.
    5. **MBR disk signature:** write 4 bytes at offset 440 (little-endian) = installer
       signature S. Derive it like `IMG_PART_SIGNATURE` but salted, e.g.
       `echo installer$(SOURCE_DATE_EPOCH)$(LINUX_VERMAGIC) | $(MKHASH) md5 | cut -b1-8`. The
       live cmdline uses `root=PARTUUID=S-03`. Confirm xorriso leaves bytes 440–443 alone, or
       write them after.
- Output: `bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-installer.iso`.

### 4. `package/custom/openwrt-installer` (new; `PKGARCH:=all`)

**`DEPENDS`:** `+python3-light +whiptail +sfdisk +e2fsprogs +btrfs-progs +xfs-mkfs +dosfstools`
`+lsblk +blkid +grub2-bios-setup +openssl-util`. Register it in
`configs/custom-package-updates.json` as `{"provider": "local", …}`.

**Files:**

| Installed path | Purpose |
| --- | --- |
| `/usr/sbin/openwrt-installer` | TUI main loop (step index; Cancel/Esc goes back one step); `--answers FILE [--dry-run]` non-interactive mode |
| `/usr/lib/openwrt-installer/core.py` | Pure, host-testable: layout planning, GUID scheme, sfdisk script, UCI batch text, grub.cfg rewrite, answers validation, lsblk/sysfs parsing |
| `/usr/lib/openwrt-installer/apply.py` | Executes a validated plan |
| `/usr/libexec/openwrt-installer/firstboot` + `openwrt-installer-firstboot.service` | Regular user + GNOME on first boot |
| `openwrt-installer.target` | `Wants=openwrt-installer@tty1.service openwrt-console@tty2.service openwrt-console@ttyS0.service`, `AllowIsolate=yes` |
| `openwrt-installer-serial.target` | `Wants=openwrt-installer@ttyS0.service openwrt-console@tty2.service` |
| `openwrt-installer@.service` | `TTYPath=/dev/%I`, `StandardInput=tty`, `StandardOutput=tty`, `TTYReset=yes`, `Environment=TERM=linux`; after exit it offers restart/shell/reboot |

**Answers JSON** is what the TUI produces and what `--answers` consumes. It contains hashes only,
never plaintext passwords (PPPoE's password is necessarily plaintext, as in UCI):

```json
{"disk": "/dev/nvme0n1",
 "partitions": [{"role": "boot", "size_mib": 512}, {"role": "rom", "size_mib": 1024},
                {"role": "overlay", "fs": "ext4", "size_mib": null},
                {"role": "data", "fs": "xfs", "size_mib": 20480}],
 "network": {"wan_port": "eth1", "lan_ports": ["eth0", "eth2"],
             "lan": {"ipaddr": "192.168.1.1", "netmask": "255.255.255.0",
                     "dhcp": true, "start": 100, "limit": 150},
             "wan": {"proto": "dhcp"}, "ipv6": true},
 "firewall": {"masq": true, "fullcone": false, "lan_to_wan": true},
 "accounts": {"root_password_hash": "$6$...",
              "user": {"name": "alice", "password_hash": "$6$...", "gnome_autostart": true}}}
```

Per-protocol `wan` fields: PPPoE `{"proto":"pppoe","username":…,"password":…}`; static
`{"proto":"static","ipaddr":…,"netmask":…,"gateway":…,"dns":[…]}`; `{"proto":"none"}`. In the
`partitions` list, `size_mib: null` means the rest of the disk.

**TUI screens** (whiptail; keep each screen to a few items):
1. **Welcome:** Install / Shell / Reboot.
2. **Target disk:** `lsblk -J -b -o NAME,PATH,SIZE,MODEL,TRAN,RO,RM,TYPE`, disks only. Hide the
   installer media (the disk of the `/rom` device), `ro=1`, loop, sr, zram and mmcblk boot0/1.
3. **Partitioning:**
   - "Guided – use entire disk (recommended)" → overlay filesystem radiolist (ext4/btrfs/xfs) →
     layout preview.
   - "Manual" → list p1 boot / p2 rom / p3 overlay / extra / free space. Select a partition to
     resize or change its filesystem (overlay: ext4/btrfs/xfs; extra: ext4/btrfs/xfs/unformatted);
     select free space to create an extra partition. Extra partitions can be deleted. "Done".
   - Only checks: boot ≥ 64 MiB, rom ≥ squashfs size, overlay ≥ 2 GiB, everything fits. Sizes are
     MiB-aligned.
4. **Network ports:** NICs where `/sys/class/net/X/device` exists and that aren't wireless
   (`wireless/` or `phy80211` absent). Show MAC, driver (`device/driver` basename) and carrier.
   Run `ip link set X up` so carrier is visible, and offer "Refresh".
   - WAN radiolist, including "None"; LAN checklist.
   - Defaults: eth0 LAN, eth1 WAN, others LAN; with one NIC, LAN only and WAN None.
5. **LAN:** field menu with current values plus "Continue": IP 192.168.1.1, netmask
   255.255.255.0, DHCP on, start 100, count 150.
6. **WAN:** DHCP (default) / PPPoE (user, password) / Static (IP, mask, gateway, DNS) / None; then
   a yes/no "Enable IPv6" (default yes).
7. **Firewall:** text summary of the stock zones (lan: accept/accept/accept; wan: reject input,
   accept output, reject forward). Checklist: NAT masquerade on WAN [on], full-cone NAT [off]
   (only meaningful with NAT), LAN→WAN forwarding [on].
8. **Accounts:**
   - root password, twice, required;
   - username, optional, `^[a-z_][a-z0-9_-]{0,31}$`, not an existing account in the target
     passwd;
   - user password twice;
   - "Start GNOME automatically at boot" (default yes, only if a user is given).
   - Hash immediately with `openssl passwd -6 -stdin`.
9. **Summary:** textbox with everything. Then "ALL DATA ON /dev/X WILL BE ERASED. Install?"
   (`--defaultno`), a `--gauge` progress bar, and "Installation complete. Remove the USB stick
   and press Enter to reboot."
   - On error: msgbox with the last lines of `/tmp/openwrt-installer.log` and options to go back
     to the summary or open a shell.

Validation stays minimal: IPv4 parse with `ipaddress`, the DHCP pool fits inside the LAN subnet,
passwords match, username syntax, partition minimums. Nothing else.

**`apply.py` steps:**
1. Unmount anything on the target. `wipefs -a /dev/X`. Then an sfdisk script:
   - `label: gpt`, `label-id: G..00` (random with the last byte 00);
   - `start=2048` for p1, MiB-aligned sizes;
   - types: ESP `C12A7328-F81F-11D2-BA4B-00A0C93EC93B`, Linux
     `0FC63DAF-8483-4772-8E79-3D69D8477DE4`, BIOS boot `21686148-6449-6E6F-744E-656564454649`;
   - `uuid=G..0N`; names `boot`, `rootfs`, `rootfs_data`, `data`;
   - **p128** BIOS boot at `start=34, size=2014`, `uuid=G..80`.
   - sfdisk's dump format takes the partition number from the device name in the line, e.g.
     `/dev/nvme0n1p128 : start=34, …`. **Verify early;** if it doesn't work, use another
     method, but keep boot=1, rom=2, overlay=3.
   - Then `partx -u`, `udevadm settle`, and wait for device nodes.
2. **rom:** `dd if=<stick p3 = /rom's device> of=<X>2 bs=4M iflag=count_bytes count=<size> conv=fsync`,
   then read back that many bytes and compare SHA-256 with the manifest.
3. **boot:** `mkfs.fat -F 32 -n kernel -i <random 8 hex> <X>1`, mount, `cp -a` the
   `install/esp/` tree. Then rewrite `boot/grub/grub.cfg`:
   - replace the manifest's build `PARTUUID=…` with `PARTUUID=G..02` (all entries, including
     procd recovery and failsafe);
   - replace `search -l kernel -s root` with `search --fs-uuid --set=root <XXXX-XXXX>`, as
     kernelctl does later.
4. **BIOS:** `device.map` `(hd0) /dev/X`, then
   `grub-bios-setup -m device.map -d <esp>/boot/grub -r hd0,gpt1 /dev/X`. UEFI uses the removable
   path `\EFI\BOOT\BOOTX64.EFI`, so there are no NVRAM writes and no efibootmgr.
5. **overlay:** `mkfs.ext4 -F -L rootfs_data`, `mkfs.btrfs -f -L rootfs_data` or
   `mkfs.xfs -f -L rootfs_data`. Mount, `mkdir upper work`, `ln -s 2 .fs_state`.
6. **Target root:** mount `<X>2` squashfs read-only at `/run/openwrt-installer/rom`, and
   `overlay` (`lowerdir=rom,upperdir=ov/upper,workdir=ov/work`) at
   `/run/openwrt-installer/target`. Then:
   - **network:** write from scratch with
     `uci -c /run/openwrt-installer/target/etc/config batch`:
     - `loopback`, `globals` (`ula_prefix` random `fdXX:XXXX:XXXX::/48` only with IPv6);
     - `device br-lan` (type bridge, ports);
     - `lan` (static, `ipaddr`, `netmask`, `ip6assign 60` with IPv6);
     - `wan` (`device <wan>`, proto dhcp/pppoe/static; PPPoE `ipv6 'auto'` with IPv6, otherwise
       `ipv6 '0'`);
     - `wan6` (`proto dhcpv6`, `device <wan>`; dhcp/static only and only with IPv6).
   - **dhcp:** batch-edit the stock file:
     - `dhcp.lan.start/limit`, or `dhcp.lan.ignore=1` when DHCP is off;
     - without IPv6, `dhcp.lan.dhcpv6/ra='disabled'`.
   - **firewall:** batch-edit the stock file. Find sections by `name` via
     `uci -c … -X show firewall`:
     - `masq` on the wan zone;
     - `@defaults[0].fullcone='2'` when chosen;
     - add or delete the lan→wan `forwarding`.
   - Set root's hash in field 2 of the target `/etc/shadow` with an in-place line edit.
   - Write `/etc/openwrt-installer/firstboot.json` (mode 0600, root:root) with the user, hash
     and GNOME flag, and `/etc/openwrt-installer/install.json` (summary, no secrets).
   - Format any extra partitions (label `data`, `data2`, …), not mounted.
7. Unmount target, rom, overlay and ESP. `sync`.

**First boot: `openwrt-installer-firstboot.service`.**
- `Type=oneshot`.
- `After=openwrt-services.service dbus.service systemd-logind.service`.
- `ConditionPathExists=/etc/openwrt-installer/firstboot.json`.
- `WantedBy=multi-user.target`, linked in the package.

The script:
1. `useradd -m -G sudo USER` (the `sudo` group comes from `99-multiuser`, which runs in
   `openwrt-services`);
2. `usermod -p HASH USER`;
3. if autostart, `desktop-setup USER`;
4. on success, `rm` `firstboot.json`; on failure, leave it and log to the journal.

On systems not installed by the ISO the file is absent and the unit is skipped.

### 5. Config, docs, bookkeeping

- `configs/installer-iso.config` fragment: `CONFIG_INSTALLER_ISO_IMAGES=y`,
  `CONFIG_PACKAGE_openwrt-installer=y`, `CONFIG_PACKAGE_btrfs-progs=y`,
  `CONFIG_PACKAGE_whiptail=y`.
  - Merge with
    `./scripts/kconfig.pl + .config configs/installer-iso.config > .config.new && mv .config.new .config && make defconfig`.
  - Preserve the existing `.config`. Update `configs/x86-64-systemd-desktop.config` only after an
    accepted build.
- `docs/installer-iso.md` (guide) and `docs/installer-iso-validation.md` (hand-written record:
  image path and SHA-256, `| Check | Result |` table, scope, Evidence directory outside the
  repo). The guide covers:
  - writing the stick raw (`dd`, Etcher, Rufus *DD mode*). Rufus ISO mode, Ventoy and optical or
    virtual-CD boot are unsupported because root is a USB partition, not a file in ISO9660;
  - the screens and defaults, the disk layout, first-boot behavior, the `/boot` and kernelctl
    layout, the tty2 shell, and recovery.
- `package/base-files/system-description.systemd.md`: describe the installer and bump base-files
  `PKG_RELEASE`. That bump also covers `79_move_config`.
- `CLAUDE.md`: a short subsection under Architecture.
- Commits: focused, explicit-path staging, subjects like `fstools: mount btrfs and xfs overlay
  partitions`, `grub2: build hybrid installer boot images`, `x86: build installer ISO from a clean
  rootfs`, `openwrt-installer: add TUI installer`, `base-files: …`, `docs: …`. No feed changes:
  whiptail and btrfs-progs only need selecting.

## Implementation order (risky spikes first)

1. **Boot spike.** Do the fstools patch, `79_move_config`, the grub2 images and
   `Build/installer-iso` with a stub `openwrt-installer` that just execs a shell. Boot the ISO as
   a **usb-storage** stick under OVMF and SeaBIOS. Confirm:
   - GRUB finds its config in both modes;
   - root mounts from S-03 and a tmpfs overlay is used (nothing written to the stick);
   - `systemd.unit=openwrt-installer.target` starts under the fork's init;
   - udev coldplug loads NIC drivers (otherwise run `/sbin/kmodloader` at installer start);
   - sfdisk creates p128;
   - an installed target with an ext4 `rootfs_data` p3 mounts as `/overlay`.
2. `core.py` plus `scripts/tests/test-openwrt-installer.py`.
3. TUI, `apply.py`, the first-boot unit.
4. Full `build-only`, the VM matrix, docs.

## Verification

- **Host tests:** `python3 scripts/tests/test-openwrt-installer.py`. Load `core.py` via
  `SourceFileLoader`. Cover:
  - guided and manual layouts, minimums, alignment;
  - the GUID scheme and sfdisk script text;
  - UCI batches for dhcp/pppoe/static/none × IPv6 on/off × firewall toggles. Also apply them with
    `staging_dir/host/bin/uci` when present and assert on `uci show`;
  - the grub.cfg rewrite;
  - disk and NIC parsing from canned `lsblk -J` and a fake sysfs tree.
  - Also run `git diff --check`.
- **Builds:** `make package/system/fstools/{clean,compile} V=s`,
  `make package/custom/openwrt-installer/compile V=s`, then
  `python3 scripts/build-and-publish.py build-only -j12 V=s` (no publication).
- **Static ISO checks:**
  - `xorriso -indev <iso> -report_el_torito plain`;
  - `fdisk -l <iso>` shows p1 ISO, p2 EF, p3 83 and signature S;
  - `unsquashfs -l` on p3 contains `etc/uci-defaults/99-multiuser` and **not**
    `99-zz-example-user`, `99-zzz-local-settings`, `etc/config/passwall` or `etc/config/network`;
  - `combined-efi.img` is byte-identical to the pre-refactor build of the same inputs.
- **VM gate:** new `scripts/tests/test-installer-iso-vm.py`. Reuse `scripts/test-image-network.py`
  helpers (QEMU q35, OVMF var copies, serial log, LAN client VM).
  - Attach the exact ISO as `-device usb-storage` plus an empty target disk.
  - On the ttyS0 shell: write the answers JSON with a heredoc, run
    `openwrt-installer --answers`, power off, then boot the target disk alone.
  - Matrix:
    - (a) OVMF + NVMe + ext4 + WAN DHCP + IPv6 + user with GNOME autostart;
    - (b) SeaBIOS + SATA + btrfs + static WAN + IPv6 off;
    - (c) OVMF + virtio + xfs + PPPoE (config only, no server) + full-cone.
  - Checks:
    - `findmnt /overlay` shows p3 and the chosen filesystem, and `/boot` is p1;
    - `kernelctl list` works;
    - `systemctl --failed` is empty;
    - the LAN client gets a lease inside the configured pool and reaches LuCI over HTTPS (200)
      and SSH with the chosen root password;
    - `nft list ruleset` shows masquerade, LAN→WAN forwarding and full-cone as chosen;
    - the user exists, is in `sudo`, and `loginctl` shows their seat0 GNOME session;
    - `firstboot.json` is gone;
    - no `example-user` account and no personal configs.
  - One manual TUI walkthrough on the "serial console" GRUB entry, recorded in the validation
    doc.
- **Regression:**
  - the same build's `combined-efi.img` still uses its internal F2FS overlay;
  - an extroot VM like `docs/extroot-upgrade-validation.md` still mounts its ext4 extroot;
  - check that btrfs/xfs `.ko` files land in kernelctl's per-kernel `initramfs.gz` (from
    `modules-boot.d`).
- **Scope:** no physical router, flashing, feed publication or push.

## Open risks to settle during the spike

- GRUB hybrid boot details: `i386-pc-eltorito` plus `boot_hybrid.img` with `--grub2-boot-info`
  for USB-BIOS, and the El Torito EFI entry pointing at appended partition 2. Mirror
  `grub-mkrescue`'s xorriso invocation if something is off.
- Whether xorriso writes the MBR NT disk signature itself. Overwrite bytes 440–443 after.
- sfdisk support for partition number 128.
- Whether anything in `sysinit.target` under the fork assumes OpenWrt services
  (`openwrt-systemd-prepare`) when booted into the installer target.
- Physical machines with several disks: the combined image's embedded GRUB early config tries
  `(hd0,gpt1)` first, then falls back to the boot device. Test a VM with two disks.
