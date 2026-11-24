# Installer components implementation progress

## 2026-11-16

The independent installer fixes
preserve firewall/port/WAN inputs on return, keep LAN number errors on
the LAN page, reject static WAN network/broadcast addresses and overlapping LAN/WAN
subnets, preserve the original installation error when unmount cleanup also fails,
include disk model/capacity/available serial in confirmation, and use installation
media wording with the LAN management address on completion. The installer package
release increases from 3 to 4. Existing passwords are retained on revisiting PPPoE.

Validation: test-openwrt-installer.py ran 12 tests, 11 passed and one skipped because
host UCI is absent. The UCI matrix's actual-UCI branches also did not execute.
test-installer-optical.py ran two tests, one passed and one skipped for missing
prepared target root/config. git diff --check passed. An injected boot-copy plus unmount failure verifies
that the reported exception retains the installation failure and cleanup detail.

The package compile triggered broad dependency rebuilds and was interrupted
(exit 130). This run left package build acceptance pending.

## 2026-11-19

- **Ordinary installer build.** The full desktop build manifest at
  `bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic.manifest` lists
  `openwrt-installer 1-r4` and `linux-image-7.3.5-70-openwrt` (generation-66
  also produced a full build and installer ISO on 2026-11-17).
- **Ordinary installer VM.** The
  [systemd-only validation](systemd-only-validation.md#最终编辑后的主机与-vm-验证结果)
  records a separate generation-70 installer ISO with SHA-256
  `5af7387b0e5acfdba191ed0d10664fa8c7efe33866499e57ff0f542c3d569ab1`.
  Its receipt covers hybrid boot metadata and USB installs under BIOS and UEFI
  with ext4, btrfs and xfs, including a GNOME first boot. The ISO in `bin/systemd`
  at review time had SHA-256
  `42499348ad9c4e82732a7c4c54f15cdfd6e0e7f35fba5600f9b9db5b540fd3fb`.
  The VM result applies to the image identified in the receipt.
- **Shared packages and pure-router image.** Commit `a5650a322c` adds the
  pure-router build profile and decouples `xdg-desktop-portal` from the Flatpak
  runtime and `virt-manager` from `openwrt-desktop`. The
  [decoupling validation](systemd-router-decoupling-validation.md) records
  strict Kconfig, isolated APK builds and dependency inspection, pure-router
  VM network and failsafe coverage, and a subsequent signed userspace upgrade
  on the existing full desktop router. Optional application runtime cases
  remain pending.

Component installation implementation and validation (2026-11-19):

- **RDP package split & desktop-setup**: Split `openwrt-desktop` (`35 -> 37`) into
  `openwrt-desktop-core` (without `gnome-remote-desktop` or RDP scripts, and adding
  explicit `+shadow-su` discovered during `gnome_core` VM firstboot),
  `openwrt-desktop-rdp` (`+openwrt-desktop-core +gnome-remote-desktop`), and the
  `openwrt-desktop` metapackage (`+openwrt-desktop-core +openwrt-desktop-rdp +rtkit`)
  for rolling-upgrade compatibility. Added `--no-autostart` to `desktop-setup` and
  guarded `gnome-remote-desktop.service` in `desktop-gnome-remotes`. Updated
  `openwrt-desktop-audio` (`r5`), `openwrt-desktop-ime` (`r5`), `openwrt-flatpak`
  (`r11`), and `openwrt-appimage` (`r5`) to depend on `+openwrt-desktop-core`.
- **Catalog, base rootfs & offline signed repo assembler**: Added
  `configs/installer-components.json` (format version 2, 9 components + curated
  base router/ops top-level package list including `coreutils-chown`, `coreutils-kill`,
  `coreutils-realpath`, `coreutils-sleep`, `coreutils-stat`, and `shadow-su` +
  forbidden-leak assertions) and `scripts/build-installer-components.py`. Updated
  `scripts/build-installer-iso.py` and `target/linux/x86/image/Makefile`
  (`Build/installer-iso`) to assemble the clean base squashfs and embed the signed
  offline APK repository, `components.json`, and public key under `/install/components`.
- **Installer (`openwrt-installer` `1-r5`)**: Updated `core.py`, `apply.py`, `tui.py`,
  and `firstboot` to support component selection (default all ON, dependency
  validation preserving user selection, `--answers` `components` list), pre-wipe
  offline APK simulation + SHA-256/signature/identity verification + overlay space
  enforcement (unpacked + 15% overhead + 1 GiB reserve), offline APK installation
  into the merged target overlay (`--commit-hooks=no --force-no-chroot --preserve-env`
  with `IPKG_INSTROOT`), and component-aware firstboot (`desktop-setup [--no-autostart]`,
  `desktop-audio-setup`).
- **Full build artifacts (`python3 scripts/build-and-publish.py build-only -j12 V=s`, generation `71`, `7.3.5-71-openwrt`)**:
  - Component ISO: `bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-installer.iso`
    (SHA-256 `8381563e2248363047a03ff5e8bf58c2200a723443665fef923e38d19ebfbe4c`)
  - Same-build combined EFI image: `bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz`
    (SHA-256 `019734c82a6beda3958475f00a87c7a3a90c878de4c8ab7ca3d870b650d0566a`)
- **Host & real-APK validation (post-final-edit)**:

  | Check | Result |
  | --- | --- |
  | `scripts/tests/test-installer-components.py` | Pass (9/9) |
  | `scripts/tests/test-openwrt-installer.py` | Pass (11 passed, 1 skipped for absent host UCI) |
  | `scripts/tests/test-installer-optical.py` | Pass (1 passed, 1 skipped for target root/config args) |
  | `scripts/tests/test-custom-package-updates.py` | Pass (49/49) |
  | `scripts/tests/test-systemd-router-decoupling.py` | Pass (12/12) |
  | Real-APK host preflight, untrusted-key reject, offline install, & rolling upgrade sim (`openwrt-desktop` `35 -> 36`) | Pass (ran before `r37` `+shadow-su` addition) |

- **Disposable KVM/QEMU validation (`scripts/tests/test-installer-components-vm.py`, evidence dir `/srv/openwrt-validation/installer-components-validation-20261119/`)**:

  | Check | Result |
  | --- | --- |
  | ISO static checks (`format_version=2`, hybrid BIOS/UEFI, signed `/install/components`, public key only, clean base squashfs `1019` pkgs, `362` offline APKs) | Pass |
  | Case 1: `base_only` (OVMF, USB, NVMe, ext4, `1019` pkgs, LAN client DHCP/LuCI HTTPS 200/SSH, local HTTP feed `apk upgrade`, `failsafe=true` recovery) | Pass (`receipt.json`) |
  | Case 1 re-run (`kctl_verify/receipt.json`): multi-generation `kernelctl` install, reboot-bless, & rollback (`7.3.5-71-openwrt -> 7.3.5-70-openwrt -> rollback 7.3.5-71-openwrt`) | Pass |
  | Case 2: `gnome_core` (BIOS, CD-ROM `/dev/sr0` loop, SATA, btrfs, `1207` pkgs, no RDP/Flatpak/Audio, `gnome_autostart=false` -> manual start, `FileChooser`/`ScreenCast` portals, `pipewire.socket`, `gnome.png`, LAN client, `apk upgrade`) | Pass |
  | Case 3: `full_desktop` (OVMF, USB, virtio, xfs, `1381` pkgs, autostart GNOME + `openwrt-fcitx5`/`pipewire`/`wireplumber`/`org.freedesktop.portal.Flatpak`/`virsh`/`podman`/`flatpak`, `gnome.png`, LAN client, `apk upgrade`) | Pass |
  | Case 4: `headless_virt_containers` (BIOS, CD-ROM `/dev/sr0`, virtio, ext4, `1115` pkgs, `virsh`/`qemu`/`podman`/`distrobox` without GNOME or `virt-manager`, LAN client, `apk upgrade`) | Pass |
  | Same-build `combined_regression` (internal F2FS `/overlay` & `/boot`) | Pass |

- **Scope boundary**: All builds and validations ran locally on host and disposable KVM VMs only. LAN APK feed publication (`/srv/openwrt-feeds`) and physical device installation/client streaming tests remain unexecuted pending explicit authorization.

### Review fixes, generation 72 build & feed publication (2026-11-19)

- **Fixes applied**:
  - `package/custom/openwrt-installer/files/apply.py`: Compute component unpacked size from `apk query --available --fields name,version,installed-size --format json` (and parse `apk-tools` 3.x `OK:` delta when falling back) instead of the missing `After this operation` line so full-component selection uses actual unpacked size (`2858 MiB` minimum overlay rather than `3241 MiB`) and accepts 4.5 GiB disks (`3070 MiB` overlay). Anchor offline repository signature verification in both `preflight_components()` and `install_components()` to the booted/written base system's `/rom/etc/apk/keys` rather than `/install/components/keys`.
  - `config/Config-images.in`, `configs/installer-iso.config`, `target/linux/x86/image/Makefile`, `scripts/build-installer-components.py`, `docs/installer-iso.md`: Require `CONFIG_SIGNED_PACKAGES=y` and valid signing keys (`BUILD_KEY_APK_PUB` / `BUILD_KEY_APK_SEC`) for `CONFIG_INSTALLER_ISO_IMAGES`, remove `--allow-untrusted` build paths, verify that the build repository contains the full desktop-profile base and all nine components before assembling the ISO, and document the prerequisite.
  - `package/base-files/Makefile` (`PKG_RELEASE` `.19 -> .20`) and `package/custom/sunshine/Makefile` (`PKG_RELEASE` `12 -> 13`): Bump releases for changed content/binaries before publication.
- **Generation 72 build & publication (`./scripts/build-and-publish.sh -j12 V=s`, `7.3.5-72-openwrt`)**:
  - Component ISO: `bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-installer.iso`
    (SHA-256 `7f1cd5cc0e8b24b0ae05c31b355eb93808f5affe3aa1b7f0ac119d77a6f8a29f`)
  - Same-build combined EFI image: `bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz`
    (SHA-256 `3ed4aa3901efd2c6b2c22b393226ac019dd809d4c5803934606f4cfcd9475347`)
  - Published userspace snapshot: `/srv/openwrt-feeds/public/snapshots/20261119T102145.702266Z`
  - Published kernel snapshot: `/srv/openwrt-feeds/public/kernel-snapshots/1795083724642370849` (`7.3.5-69-openwrt`, `7.3.5-70-openwrt`, `7.3.5-72-openwrt`; `upgrade_preflight` `passed`, `elf_transition` 1389 packages / 2464 ELF files)
- **Host & real-APK validation (post-generation-72 build)**:

  | Check | Result |
  | --- | --- |
  | `scripts/tests/test-installer-components.py` (includes real `apk-tools 3.0.5` preflight on gen-72 ISO, 4.5 GiB disk check, rogue-key rejection, and pure-router/unsigned build guards) | Pass (12/12) |
  | `scripts/tests/test-custom-package-updates.py` | Pass (49/49) |
  | `git diff --check` | Pass |

- **Scope boundary**: The 4-case KVM VM suite above was run against the generation-71 ISO and has not yet been re-run against the generation-72 ISO; physical router installation/upgrade/reboot and desktop/streaming client tests remain unexecuted.
