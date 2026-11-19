# Upstream synchronization — 2026-11-19

Merged OpenWrt through `ecd9120f0451` (8 incoming commits) as `5009212efb`.
Independent feed merges incorporate 23 `packages` (`8c1e6ab5d`), 1 `luci`
(`9fcb44feeb`), and 2 `passwall_luci` (`4d6d8bd8`) commits. `passwall_packages`,
`routing`, `taskplan`, `telephony`, and `video` were already current. All merges
retain their previous local HEAD as an ancestor; no reset, rebase, force update,
or push was used.

Preservation receipts, backup refs (`backup/pre-upstream-20261119T020337Z`),
incoming path inventories, strict Kconfig copy, and kernel patch-application
evidence are in `.git/pull-preserve/20261119T020337Z/`. All 11 repository
backups, stashes, `.config`, and unrelated local/untracked files are preserved.

## Integration and custom recipes

- Main-tree merges cleanly (`wireguard-tools` per-peer validation in
  `wireguard.uc`, `odhcpd` 2026-11-17 `4580970d`, plus `qualcommax` IPQ50xx and
  `realtek` target updates) without overlapping local systemd, kernel, or
  network modifications.
- Advance `wireguard-tools` `PKG_RELEASE` from `3` to `5` (`9b4c77fd2a`):
  incoming `1.0.20260223-r3` changes `files/wireguard.uc` and maps via
  `configs/apk-elf-rebuilds.mk` to `1.0.20260223-r4`, which collides with the
  already-published `wireguard-tools-1.0.20260223-r4.apk`. The ledger is left
  unchanged.
- Advance `feeds/packages` `net/curl` `PKG_RELEASE` from `2` to `4`
  (`426ce9fd4`): upstream folded `net/libcurl-gnutls` into `net/curl` as
  `VARIANT:=gnutls` and bumped `PKG_RELEASE` to `2`, which maps via
  `configs/apk-elf-rebuilds.mk` to the already-published `curl-8.23.0-r3.apk`
  and `libcurl4-8.23.0-r3.apk`. Removed the resulting stale
  `package/feeds/packages/libcurl-gnutls` symlink before regenerating feed links.
- Other `feeds/packages` updates (`dovecot` 2.3.21.1 + CVE backports,
  `pigeonhole` + CVE backports, `fluent-bit` 5.1.5, `netdata` system SQLite,
  `micropython-lib` 1.29.0, `mpremote` 1.29.0, `subversion` 1.15.0,
  `keepalived`, `tailscale` 1.104.6, `udp-broadcast-relay-redux`, `mpd` 0.24.17,
  `fio` 3.43, `fish` build-system Rust support, and `uvol`), `feeds/luci`
  (`luci-mod-dashboard` wireless check), and `feeds/passwall_luci` (WireGuard
  and MASQUE subscription/URI support) merge cleanly with zero conflicts.
- `python3 scripts/update-custom-packages.py --check` checked all 188 custom
  entries with zero errors and zero eligible updates: 147 current, 36 locally
  maintained, and the same 5 pinned review entries (`flatpak` 1.19.2 prerelease,
  dual-slot `gcr3` / `libgtk3`, and upstream tag noise in `intel-media-driver` /
  `libibus`).

## Linux 6.18 to 7.3 review and mainline kernel check

- `python3 scripts/update-mainline-kernel.py --check` reports Linux `7.3.5` is
  `current` (SHA-256
  `8f293f83d54f0b7b9be56863ebc5e4ea79d73e530b4ae55c572be97ef39f0990`).
- Zero incoming files touch `target/linux/generic/` or `target/linux/x86/`.
  Incoming kernel changes are board-specific (`qualcommax` IPQ50xx and `realtek`
  `mdio-realtek-otto-serdes.c` / DTS / `hwmon_fancontrol`) and do not belong in
  the x86/64 Linux 7.3 port.
- Across the full 586-patch generic/x86 6.18 inventory, no new x86/generic
  backport candidates exist; the only four unregistered 6.18 patches remain the
  previously reviewed non-x86 entries (`hack-6.18/301-03-mips-*` and
  `pending-6.18/799-01..03` MediaTek WED, plus the offset-only `799` refresh).
- All 355 carried Linux 7.3 patches match their registered SHA-256 hashes and
  apply with `--fuzz=0` to a fresh extraction of verified Linux `7.3.5` plus
  current generic/x86 overlays.

## Validation scope

Feed index regeneration (`./scripts/feeds update -i -a`), package link
installation (`./scripts/feeds install -a`), all nine nonempty feed indexes,
zero broken `package/feeds` symlinks, and strict Kconfig validation
(`conf --fatalrecursive --olddefconfig` on an isolated copy of `.config` with
zero selected-symbol differences and `.config` SHA-256
`dcb2fdb46b7fe49c5623bea739eba60a1516945dec093b6300c67b1ff999d821` preserved)
all pass.

Host test suites pass:
- `scripts/tests/test-mainline-kernel-updates.py` (20 tests)
- `scripts/tests/test-kernel-build-inputs.py` (7 tests)
- `scripts/tests/test-custom-package-updates.py` (49 tests)
- `scripts/tests/test-package-metadata-kconfig.py` (4 tests)
- `scripts/tests/test-elf-abi.py` (23 tests)
- `scripts/tests/test-ucode-abi.py` (6 tests)
- `scripts/tests/test-luci-firewall-fullcone.js` and
  `scripts/tests/test-luci-needrestart.js`

Source downloads, SHA-256 checks, and patch preparation (`make .../prepare`)
pass for `wireguard-tools` (`1.0.20260223-r5`), `odhcpd-ipv6only`
(`2026.11.17~4580970d-r1`), and `curl` (`8.23.0-r4`).

No full firmware or kernel generation build, VM validation, feed publication,
Git push, or router deployment was performed in this synchronization.
