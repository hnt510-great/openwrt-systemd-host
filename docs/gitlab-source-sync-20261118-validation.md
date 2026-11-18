# GitLab source synchronization validation (2026-11-18)

Integrated GitLab main updates after `8b607ac3994bf875a798ffa444701aa52cb7cc5e`
through `7d58639eb0f062584fb656e05db26f2e7cd1e223` onto the public tree on
branch `sync/gitlab-20261118`. All 249 non-merge commits (207 OpenWrt upstream
commits across three upstream merges `7a085bfd72`, `44839833a8`, and
`712beefa91`, plus 42 local integration commits) have individual provenance
records (`GitLab-source:` trailers). Original author names, email addresses,
dates, and `Signed-off-by` / `Co-Authored-By` / `Suggested-by` / `Tested-by`
trailers were preserved and verified against GitLab. Private GitLab history is
not a merge parent.

Major changes integrated include mainline Linux 7.3.5 and SDIO initialization
backports, making systemd the sole normal x86/64 init with native OpenWrt
failsafe (`openwrt-systemd-only` + `auxiliary.slice` supervision for `cron`,
`nlbwmon`, and `ddns-go` + `nas.slice` supervision for `samba4`, `wsdd2`, and
`avahi-daemon` + first-upgrade native unit enablement + LuCI firmware flashing
removal), `systemd-udev` 262-r14 reviewed device boundaries and zstd/lz4/elfutils/bpf
support (`262-r15`), `openwrt-desktop` TPM2 keyring credential sealing (`r32`–`r34`)
and GNOME Shell screenshot/screencast UI, `irqbalance` per-netdev CPU pools,
`router-audit` default-off opt-in collection, `openwrt-installer` static WAN
validation and `spice-gtk` GL scanout redraw fixes, x86 `split_lock_detect=off`,
and upstream target/package updates (`mbedtls` 3.6.8, `odhcpd`, `ubox`, `procd`,
`realtek` RTL8214QF/Hasivo S5800W, `airoha` AN7583, `sunxi` A523/A527, `ramips`).

Merge and conflict resolutions against public-only tree differences:

- `package/custom/openwrt-desktop/files/desktop-setup` (`4db510e370`): merged
  TPM2 keyring credential sealing with the public `--keyring-password-stdin`
  flag; also updated `scripts/tests/test-desktop-setup.py` (`0556cb2f35`) to
  mock `systemd-analyze` in `KeyringStdinTests` so host TPM2 presence does not
  trigger real `systemd-creds` encryption in the plaintext-stdin unit test.
- `package/kernel/linux/modules/crypto.mk` (`02e70c7548`) and
  `package/system/procd/Makefile` (`c4acd16e4c`): applied the exact conflict
  resolutions from GitLab merge `44839833a8`.
- `AGENTS.md` and `CLAUDE.md`: kept deleted on the public branch while applying
  `bb5f965f5a` updates to `GEMINI.md` and keeping existing `/srv/openwrt-validation/`
  and `192.0.2.x` redactions.
- `package/custom/luci-theme-argon` (`476b1da519`): kept the public submodule
  gitlink at `9e263d988b7be4d619442f297f4105871e12808` because
  `96bd5308216e75004040a041258cc141656146e6` is not present on the public
  GitHub remote.
- `docs/desktop.md`, `docs/flatpak.md`, `docs/input-hotplug.md`, and
  `docs/virt-manager.md` (`9cfed49a54`): prepended the systemd-only deprecation
  banner onto the existing condensed public guides.
- `patches/feeds/0038-packages-python3-config-prefix.patch` and
  `configs/python3-config-feeds.json`: retained alongside incoming
  `patches/feeds/0038-packages-irqbalance-netdev-cpus.patch` and
  `configs/irqbalance-netdev-cpus-feeds.json`.
- Personal identifiers in newly added/modified documentation and guest test
  fixtures were redacted without altering author attribution, commit emails,
  or patch `From:` / `Signed-off-by:` headers: private LAN/host IPs (`192.168.2.x`)
  use `192.0.2.x`, SSH accounts (`hnt510@192.168.2.1`, `hnt51`, `ssh fedora`)
  use `router-admin@192.0.2.1` / `remote-user` / `ssh remote-host`, personal
  checkout/evidence paths (`/home/hnt510/hp_ssd/...`, `~/hp_ssd/...`,
  `/home/hnt510/Projects/...`, `/home/hnt510/.local/share/...`) use
  `/srv/openwrt`, `/srv/openwrt-validation/...`, and `~/.local/share/...`,
  and host VM UUID/PIDs in `docs/installer-spice3d-fedora-handoff-20261115.md`
  are redacted.

The seven updated ignored `feeds/*` repositories were also merged locally
(`--no-ff`, preserving existing `README*.md`, `lang/python/python3/Makefile`, and
anonymized `mesa` patch headers) and re-indexed with `./scripts/feeds update -i -a`
and `./scripts/feeds install -a`; `feeds/routing` (`2ae1f6df7b`) had zero
incoming commits:

- `feeds/packages`: `253026ac8f` (merged `gitlab/master` `eb7e31bf70`)
- `feeds/luci`: `12844e0c55` (merged `gitlab/master` `671405e5c1`)
- `feeds/video`: `91b3f3fa1e` (merged `gitlab/master` `ca6f0adb0f`)
- `feeds/passwall_luci`: `d1f30823b9` (merged `gitlab/main` `16158ae1b9`)
- `feeds/passwall_packages`: `64a41e56bc` (merged `gitlab/main` `046c300d22`)
- `feeds/taskplan`: `8417a64b29` (merged `gitlab/main` `0368067527`)
- `feeds/telephony`: `5dbc0e9150` (merged `gitlab/master` `fa3a5f0dc9`)

| Check | Result |
| --- | --- |
| Author attribution | All 249 replayed commits match original author names, emails, dates, messages, and `GitLab-source:` trailers |
| Personal marker scan | Scanned added lines across all 249 replayed commits and incoming feed commits; zero leaked personal IPs, paths, accounts, or host UUIDs (`From:`/`Signed-off-by:`/author emails preserved per policy) |
| Content parity | All 548 modified files in `main..sync/gitlab-20261118` match sanitized `gitlab/main`; diffs vs `gitlab/main` (`197` files) are confined to `184` pre-existing public deltas (`152` untouched, `32` overlapping) plus `13` newly sanitized docs and guest/unit tests |
| Whitespace (`git diff --check`) | Passed on `main..sync/gitlab-20261118` (`0` issues) |
| `scripts/feeds update -i -a` & `install -a` | Exited 0; feed indexes regenerated cleanly |
| Host Python test suite (`scripts/tests/test-*.py`, excluding VM-only `test-daed-vm.py`, `test-libvirt-secondary-drivers.py`, `test-uci-history-vm.py`) | 61 test suites passed (`test-desktop-setup.py` passed 19/19 after mocking `systemd-analyze`; `test-kernel-apk-policy.py` skipped 25 with no built kernel APKs); 9 suites failed due to host/target environment prerequisites: `test-boot-readiness.py` (5 failures in `LegacyBusOwnership`, which reads `feeds/packages/utils/dbus/files/dbus.init` after `eb7e31bf70` split `dbus-native.init`), `test-apk-source-versions.py` (pre-existing `nginx-ssl-util` error), `test-apk-transaction-journal.py` (9 errors, no static libc on host), `test-irqbalance-netdev-cpus.py` (requires prepared `irqbalance` package), `test-rtkit-desktop.py` (13 failures) and `test-sunshine-gnome.py` (1 failure, no `/usr/libexec/desktop-user-setup` on host), and CLI-argument VM harnesses `test-apk-transaction-vm.py`, `test-input-hotplug.py`, `test-installer-iso-vm.py` |
| Node.js LuCI view suites (`scripts/tests/test-luci-*.js`: all 9 suites) | All 9 suites passed |
| `scripts/tests/test-alternatives.sh` | Passed |

Scope: local source synchronization across `openwrt-systemd-host` and the
active `feeds/*` repositories plus host unit checks only. No firmware/package
build, VM execution, physical-router modification, APK feed publication, or
remote push was performed.
