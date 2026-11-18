# Upstream synchronization — 2026-11-18

Merged OpenWrt through `27663a017ad8` (19 incoming commits) as
`712beefa91`. Independent feed merges incorporate 24 packages, 1 LuCI and
2 Passwall LuCI commits. Passwall packages, routing, taskplan, telephony and
video were already current. All merges retain their previous local HEAD as an
ancestor; no reset, rebase, force update or push was used.

Preservation receipts, backup refs (`backup/pre-upstream-20261118T033529Z`),
incoming path inventories and kernel application evidence are in
`.git/pull-preserve/20261118T033529Z/`. The snapshot covers 11 repositories
and 136 existing local files, including `.config`, overlays and untracked
content. Stashes and unrelated nested repositories are preserved.

## Integration and custom recipes

- Main-tree merges cleanly (`mbedtls` 3.6.8, `odhcpd` 2026-11-16, plus
  `airoha`, `ramips`, `realtek`, `sifiveu` and `sunxi` target updates) without
  overlapping local systemd, kernel or network modifications.
- Resolve the `gst1-plugins-base` release conflict in `feeds/packages` as
  `1.28.7-r7` (above local/published `1.28.7-r6` and upstream `1.28.7-r4`)
  while accepting upstream's Raspberry Pi SAND column format patches.
  `gst1-plugins-bad` advances to `1.28.7-r6` (above published `1.28.7-r5` and
  rebuild ledger `1.28.7-r3`), adding DASH demuxer support and v4l2codecs
  negotiation fixes.
- Other `feeds/packages` updates (`netdata` 1.33.1-r6, `noto-fonts` 2026.11.01,
  `noto-fonts-cjk`, `noto-fonts-color-emoji` 2.051, `micropython` 1.29.0,
  `gperftools` 2.19.3, `libdaq3` 3.0.29, `cifs-utils` 7.9, `ddns-scripts`
  2.8.6, `nfs-kernel-server` 3.1.1, `opentracker` 2.2.1, `openvpn` 2.7.9,
  `snort3` 3.13.2.0, `travelmate` 3.1.0-r2, `librespeed-cli` 1.0.15,
  `sshpass` 1.10 and `xfsprogs` 7.2.1), `feeds/luci` (`luci-lua-runtime`
  odhcpd ubus lease query) and `feeds/passwall_luci` (IPv6 TPROXY family and
  `src_valid_mark=0` sysctl) merge cleanly while retaining local Git-derived
  Passwall LuCI revision calculation.
- The custom updater checked all 188 entries:
  - Advanced `google-chrome-bin` from `157.0.8103.78` to `158.0.8127.36`
    (SHA-256 `4696bce00b128f385a870ba2eb6eede61698f22374ea0d8e09af8a1c6543d397`).
  - Advanced `libXfont2` from `2.0.9` to `2.0.10`
    (SHA-256 `cef1f4ad9cd69f439bb1ac484bdc8f9d7f8e70215b92d8ca86b96e31513e5f9c`).
  - Advanced `libfontenc` from `1.1.9` to `1.1.10`
    (SHA-256 `daa186a49e3cc2b6fc585ca09971351e6f010f618abc6a164eda82e42e4aa4d6`).
  - Advanced `libgtop` from `2.41.3` to `2.41.4`
    (SHA-256 `d3c18158549218835a00517d9c454a2de825ac7808efe84101a8b7e2a8ab6663`).
  - Updated `xorriso` upstream catalog/source URL from `https://www.gnu.org/software/xorriso/`
    (which timed out / dropped TLS handshakes) to the canonical GNU archive
    directory `https://ftp.gnu.org/gnu/xorriso/` used by `cpio` and `gnu-time`;
    `xorriso` `1.5.8_p2` remains current.
  - The 5 review entries (`flatpak` 1.19.2 prerelease, dual-slot `gcr3` /
    `libgtk3`, and upstream tag noise in `intel-media-driver` / `libibus`)
    retain their pinned stable branches.

## Linux 6.18 to 7.3 review and Linux 7.3.5 update

- There are no incoming `target/linux/x86` changes.
- Only one incoming generic 6.18 patch was added (`c06ccca080`):
  `target/linux/generic/hack-6.18/301-03-mips-keep-module-code-out-of-the-first-32-KiB-of-a-segment.patch`,
  which modifies `arch/mips/kernel/module.c` only to work around a MIPS 24K
  EPC erratum on `ramips`/`ath79`. It is architecture-specific to 32-bit MIPS
  and does not apply to or belong in the x86/64 Linux 7.3 port. Other incoming
  kernel commits (`airoha`, `ramips`, `realtek`, `sifiveu`, `sunxi`) are
  board-specific.
- `python3 scripts/update-mainline-kernel.py --check` identified Linux `7.3.5`
  on kernel.org (SHA-256 `8f293f83d54f0b7b9be56863ebc5e4ea79d73e530b4ae55c572be97ef39f0990`).
  Linux 7.3.5 absorbs upstream commit `01739ccea21b`
  (`mtd: spi-nor: macronix: Restore fallback parameters for MX25L12805D`),
  which was previously carried as
  `target/linux/generic/backport-7.3/439-v7.4-mtd-spi-nor-macronix-Restore-fallback-parameters-for.patch`.
  That patch now reverse-applies cleanly against pristine Linux 7.3.5 and is
  removed from `backport-7.3/`, with `configs/mainline-kernel-patches.json`
  updated to classify `439` as `upstream` in `7.3.5`.
- `python3 scripts/update-mainline-kernel.py --update` verified the Linux
  `7.3.5` archive SHA-256, applied all 355 remaining carried 7.3 patches with
  `--fuzz=0`, and updated `target/linux/generic/kernel-7.3` to `7.3.5`.
- Comparing Linux 7.3.4 and 7.3.5 shows 467 changed files; the only Kconfig
  change is `lib/crypto/Kconfig` restricting `MIPS && CPU_CAVIUM_OCTEON` SHA
  defaults to `CPU_BIG_ENDIAN`, which does not affect x86/64.

## Validation scope

Feed index regeneration (`./scripts/feeds update -i -a`), package link
installation (`./scripts/feeds install -a`), nine nonempty feed indexes, zero
broken `package/feeds` symlinks, and strict Kconfig validation
(`conf --fatalrecursive` on an isolated copy of `.config` with zero
selected-symbol differences) all pass.

Unit test suites pass:
- `scripts/tests/test-mainline-kernel-updates.py` (20 tests)
- `scripts/tests/test-kernel-build-inputs.py` (7 tests)
- `scripts/tests/test-package-metadata-kconfig.py` (4 tests)
- `scripts/tests/test-custom-package-updates.py` (49 tests)

Source downloads, SHA-256 checks and patch preparation (`make .../prepare`)
pass for `mbedtls` 3.6.8, `odhcpd` 2026-11-16, `gst1-plugins-base` 1.28.7-r7,
`gst1-plugins-bad` 1.28.7-r6, `libXfont2` 2.0.10, `libfontenc` 1.1.10,
`libgtop` 2.41.4, `xorriso` 1.5.8_p2, and `google-chrome-bin` 158.0.8127.36.

No full firmware or kernel generation build, VM validation, feed publication,
or router deployment was performed in this synchronization.
