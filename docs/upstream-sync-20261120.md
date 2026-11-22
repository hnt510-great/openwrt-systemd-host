# Upstream synchronization — 2026-11-20

Merged OpenWrt through `8b34d6283fc5` (21 incoming commits) as `49f4f53f74`.
Independent feed merges incorporate 20 `packages` (`677d3dbc36`), 7 `luci`
(`ddcb46b457`), 3 `passwall_luci` (`787594fff7`), and 1 `video` (`265a75e59d`)
commits. `passwall_packages`, `routing`, `taskplan`, and `telephony` were
already current. All merges retain their previous local HEAD as an ancestor; no
reset, rebase, force update, or push was used.

Preservation receipts, backup refs (`backup/pre-upstream-20261120T015903Z`),
incoming path inventories, strict Kconfig copy, and kernel patch-application
evidence are in `.git/pull-preserve/20261120T015903Z/`. All repository backups,
stashes (`feeds/video` `stash@{0}`), `.config`, uncommitted local QEMU changes
in `feeds/packages` (`utils/qemu/Makefile` and
`utils/qemu/patches/0007-util-fdmon-io_uring-disable-iowait.patch`), and
unrelated local/untracked files are preserved.

## Integration and custom recipes

- Main-tree merges cleanly (`kernel` 6.18.60 -> 6.18.64, `toolchain` default
  GCC 14 -> 15, `mac80211` removal of `160-backports-sockaddr_unsized-is-in-6.18.57.patch`,
  `ARCH_FORCE_MAX_ORDER` / `PAGE_BLOCK_MAX_ORDER` cleanup, Realtek PHY hwmon
  patches, plus `realtek`/`qualcommax`/`mediatek`/`lantiq` target updates)
  without overlapping local systemd, kernel, or network modifications.
- Because `.config` explicitly sets `CONFIG_TOOLCHAINOPTS=y` and
  `CONFIG_GCC_USE_VERSION_14=y`, the active compiler remains pinned at GCC
  `14.4.0` rather than switching to GCC `15.3.0`.
- Resolved two version/release merge conflicts in `feeds/packages` while
  retaining all local recipe additions:
  - `libs/v4l-utils/Makefile`: updated `1.30.1-r2` -> `1.32.0-r1`, keeping
    `CONFIG_PACKAGE_edid-decode` in `PKG_CONFIG_DEPENDS`.
  - `net/krb5/Makefile`: updated `1.22.2-r2` -> `1.22.3-r1`, keeping
    `Package/krb5-dev`, `MAKE_FLAGS += WARN_CFLAGS=`, and the native header/
    pkgconfig install recipe.
- `utils/docker-compose/Makefile` merged cleanly (`5.7.0-r1` -> `5.8.0-r1`),
  retaining the removal of the `+docker` runtime dependency for Podman hosts.
- Other `feeds/packages` updates (`php8` 8.4.28, `librespeed-common`,
  `adguardhome` 1.0.0, `fsh` 4.12.0, `swig` 4.5.1, `parted` 3.8, `iperf` 2.2.2,
  `wfb-ng` 26.11, `freeipmi` 1.6.20, `crowdsec-firewall-bouncer` 0.0.38,
  `hev-socks5-tunnel` 2.20.0, `lvm2` 2.03.44, `nextdns` 1.50.2, `dhtd` 1.0.6,
  `nfs-kernel-server` 3.2.1), `feeds/luci` (`luci-theme-bootstrap` spinner,
  `luci-theme-footstrap` refactor), `feeds/passwall_luci` (batch UCI writes,
  XHTTP download DNS, Clash per-node DNS policies), and `feeds/video`
  (`qt5base` packaging/libinput fixes) merged cleanly with zero conflicts and
  zero published APK version/ledger collisions.
- `python3 scripts/update-custom-packages.py --check` checked all 188 custom
  entries with zero errors and found one eligible update:
  - `cmake-bin`: updated `4.5.0-r1` -> `4.5.1-r1` (SHA-256
    `83b71181fb62b4fe8f26067a9321448572e7a43bd04ff6c7f54a24c33698f16d`,
    report `logs/custom-package-updates/20261120T020307.001349Z/report.json`).
  - The remaining 187 entries are 146 current, 36 locally maintained, and the
    same 5 pinned review entries (`flatpak` 1.19.2 prerelease, dual-slot
    `gcr3` / `libgtk3`, and upstream tag noise in `intel-media-driver` /
    `libibus`).

## Linux 6.18 to 7.3 review and mainline kernel check

- `python3 scripts/update-mainline-kernel.py --check` reports Linux `7.3.5` is
  `current` (SHA-256
  `8f293f83d54f0b7b9be56863ebc5e4ea79d73e530b4ae55c572be97ef39f0990`).
- Zero incoming files touch `target/linux/x86/`.
- Under `target/linux/generic/`, OpenWrt bumped 6.18 from `6.18.60` to
  `6.18.64`, dropped 6 upstream backports already present in Linux 7.3.5
  (`439`, `441`, `503-01`, `734`, `755`, `856-01`), refreshed hunk context on
  58 patches (plus one rebase refresh in `pending-6.18/739-03` for the
  non-x86 MT7988 Lynxi PCS driver), removed `CONFIG_ARCH_FORCE_MAX_ORDER=11`
  from `config-6.18` (ignored on x86/64, which uses `PAGE_BLOCK_MAX_ORDER=10`),
  and added **two new generic patches** in `drivers/net/phy/realtek/realtek_hwmon.c`
  (commit `93f90a5385`):
  1. `target/linux/generic/backport-6.18/787-v7.5-net-phy-realtek-return-MDIO-read-errors-from-hwmon.patch`
     (upstream `d5b5ab50d2f6`, v7.5): checks negative return values from
     `phy_read_mmd()` in `rtl822x_hwmon_read()` instead of masking/shifting
     errors into bogus temperatures (`-2.5 C` / `-55 C`). Absent from Linux
     7.3.5; forward dry-run and sequential apply succeed with zero fuzz and
     zero offsets. Because `CONFIG_REALTEK_PHY=m` and
     `CONFIG_REALTEK_PHY_HWMON=y` are enabled in the x86/64 kernel, this is a
     **recommended backport candidate** for Linux 7.3.
  2. `target/linux/generic/pending-6.18/744-net-phy-realtek-register-hwmon-thermal-zone.patch`:
     adds `HWMON_CHANNEL_INFO(chip, HWMON_C_REGISTER_TZ)` to
     `rtl822x_hwmon_info[]` for device-tree thermal zones alongside carried
     `pending-7.3/742` and `743`. Absent from Linux 7.3.5; applies after `787`
     with zero fuzz and zero offsets. Because `drivers/hwmon/hwmon.c` gates
     `HWMON_C_REGISTER_TZ` on `hdev->of_node` and `CONFIG_THERMAL_OF`, it is a
     no-op on ACPI x86/64 and is an **optional parity candidate** only.
- This request's kernel work is a check-only applicability review: the
  repository's 355-patch Linux 7.3 stack and `configs/mainline-kernel-patches.json`
  remain unchanged pending authorization to backport. All 355 carried Linux 7.3
  patches match their registered SHA-256 hashes and apply with `--fuzz=0` to a
  fresh extraction of verified Linux `7.3.5` plus current generic/x86 overlays.
  The optional MAP-E tunnel finding remains open.

## Validation scope

Feed index regeneration (`./scripts/feeds update -i -a`), package link
installation (`./scripts/feeds install -a`), all nine nonempty feed indexes,
zero broken `package/feeds` symlinks, `git diff --check`, and strict Kconfig
validation (`conf --fatalrecursive --olddefconfig` on an isolated copy of
`.config`, preserving `.config` SHA-256
`2c24167302cd6c5e183b925aa5833c9859ab5933dc097364911f7255e815a2a5` with zero
selected-package changes and GCC pinned to `14.4.0`) all pass.

Host test suites pass:
- `scripts/tests/test-mainline-kernel-updates.py` (20 tests)
- `scripts/tests/test-kernel-build-inputs.py` (7 tests)
- `scripts/tests/test-custom-package-updates.py` (49 tests)
- `scripts/tests/test-package-metadata-kconfig.py` (4 tests)
- `scripts/tests/test-elf-abi.py` (23 tests)
- `scripts/tests/test-ucode-abi.py` (6 tests)
- `scripts/tests/test-luci-firewall-fullcone.js` and
  `scripts/tests/test-luci-needrestart.js`

Source downloads, SHA-256 verification, and patch preparation
(`make .../download .../prepare`) pass for `cmake-bin` (`4.5.1-r1`),
`v4l-utils` (`1.32.0-r1`), `krb5` (`1.22.3-r1`), `docker-compose` (`5.8.0-r1`),
and `parted` (`3.8-r1`).

No full firmware or kernel generation build, VM validation, feed publication,
Git push, or router deployment was performed in this synchronization.

## Authorized follow-up: Realtek PHY hwmon backports and GCC 15 switch

- Carried both incoming Realtek PHY hwmon patches byte-identically into the
  Linux 7.3 patch stack:
  - `target/linux/generic/backport-7.3/787-v7.5-net-phy-realtek-return-MDIO-read-errors-from-hwmon.patch`
    (SHA-256 `c7b43e3c87a9dbde33ff059f43d3d080ce6c44b33c77c4bb7bf7cbb332df2bd4`).
  - `target/linux/generic/pending-7.3/744-net-phy-realtek-register-hwmon-thermal-zone.patch`
    (SHA-256 `294e88a339b0f622f29bd9248610efc33460c565bb8b3e6f97e92d455494a1c1`).
- Removed the unused `CONFIG_ARCH_FORCE_MAX_ORDER=11` line from
  `target/linux/generic/config-7.3` to stay aligned with `config-6.18`
  (`4a90fed434`).
- Updated `configs/mainline-kernel-patches.json` (589 entries) to register
  `787` and `744` and mark the 6 upstream-dropped `6.18.61-6.18.64` backports
  (`439`, `441`, `503-01`, `734`, `755`, `856-01`) with
  `removed_in: "6.18.61-6.18.64"`.
- Verified all **357 carried Linux 7.3 patches** apply with `--fuzz=0` to a
  fresh extraction of verified Linux `7.3.5` plus overlays, `checkpatch.pl`
  reports 0 errors / 0 warnings on both patches, and the patched
  `drivers/net/phy/realtek/realtek_hwmon.c` compiles cleanly against the
  selected x86/64 Linux 7.3.5 kernel headers (isolated output under
  `.git/pull-preserve/20261120T015903Z/realtek-hwmon-compile/`).
- Switched default compiler configuration to **GCC 15 (`15.3.0`)** in
  `.config`, `configs/x86-64-systemd-desktop.config`, and
  `configs/x86-64-systemd-router.config` (`CONFIG_GCC_USE_VERSION_15=y`,
  `CONFIG_GCC_VERSION="15.3.0"`, `CONFIG_GCC_USE_DEFAULT_VERSION=y`), and
  updated `scripts/gi-target-runner` to resolve `toolchain-x86_64_gcc-*_glibc`
  from `.config` instead of hardcoding `14.4.0`.
- Strict Kconfig (`conf --fatalrecursive --olddefconfig`) passes on isolated
  copies of `.config`, `configs/x86-64-systemd-desktop.config`, and
  `configs/x86-64-systemd-router.config` with GCC `15.3.0` active and zero
  selected-package diffs. `test-mainline-kernel-updates.py` (20),
  `test-kernel-build-inputs.py` (7), and `test-package-metadata-kconfig.py` (4)
  pass. No full GCC 15 toolchain/firmware rebuild, VM validation, feed
  publication, or router deployment was performed.
