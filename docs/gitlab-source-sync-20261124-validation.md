# GitLab source synchronization validation (2026-11-24)

Integrated GitLab main updates after `c3ee9d39a516be9d21f565e7a40db8cd1c1e09af`
through `fffc3fa9e996a77c480d366d278e0431ad15f591` onto the public tree on
branch `sync/gitlab-20261124`. All 43 non-merge commits (13 OpenWrt upstream
commits across two upstream merges `bda7e87589` and `f2f9d5cd84`, plus 30 local
integration commits) have individual provenance records (`GitLab-source:`
trailers). Original author names, email addresses, dates, and `Signed-off-by` /
`Co-Authored-By` trailers were preserved and verified against GitLab. Private
GitLab history is not a merge parent.

Major changes integrated include the condensed systemd host description and
simplified `os-release` metadata, `gvfs` LAN discovery backends and
`adwaita-icons` 51.0, pluggable desktop session switcher (`desktop-ctl`,
`luci-app-desktop`) and `openwrt-desktop-base` decoupling across audio/IME/
Flatpak/AppImage/Sunshine, verified kernel generation reuse and narrower input
fingerprints, Qt 6.11.3 / KF6 6.32.0 and full KDE Plasma 6.8.3 desktop + KRdp
audio + KWin Wayland Fcitx5 integration, hardened custom package updater for
Qt6/KDE/GNOME/mozjs tracking, project documentation alignment, mainline Linux
7.3.6 (generation 87) and cross-ABI APK immutability enforcement, `daed`
upgrade to `dae` core v2.1.3 with `package/custom/daed/src` submodule split and
client policy center (`2.1.3-r6`), and upstream target/package updates
(`mediatek` TP-Link EX820v, `hostapd` ucode MLD fix, `bcm47xx`/`mac80211`/
`linux-firmware` brcmsmac removal, `sunxi`, `rockchip`, `ath79`, `airoha`,
`ipq806x`).

Merge and conflict resolutions against public-only tree differences:

- `package/base-files/system-description.systemd.md` (`ab7856cbc6`): adopted
  the condensed description with `http://apk.example.invalid:8088`.
- `configs/custom-package-updates.json` (`1a6def2a22`): retained both
  `luci-app-desktop` and the public `luci-app-desktop-setup` registration.
- `package/custom/openwrt-desktop/files/{desktop-setup,desktop-gnome-keyring-setup,sessions.d/gnome}`
  (`9df196d5ea`) and `scripts/tests/test-desktop-setup.py`: forwarded the
  public `--keyring-password-stdin` option through the decoupled session plugin
  and keyring helper, and updated `KeyringStdinTests` to match.
- `docs/*` and `GEMINI.md` (`e0e31ab19d`): kept public-excluded `AGENTS.md`,
  `CLAUDE.md`, and `docs/hnt510-account.md` deleted; removed retired docs;
  adopted the refreshed documentation with personal paths, IPs, accounts, and
  domains redacted.
- `package/custom/luci-theme-argon` (`77bd79b4ff`): kept the public submodule
  gitlink at `9e263d988b7be4d619442f297f4105871e12808` because
  `2ad2facdef3f59d83cc0415e984767c90c915814` is not present on the public
  GitHub remote.
- `.gitmodules` and `docs/daed.md` (`1befffef56`): sanitized the new `daed-src`
  submodule URL to `../daed.git` and removed the retired
  `004-dae-wing-default-lan-interface-for-new-configs.patch`.
- Personal identifiers in newly added/modified documentation, `.gitmodules`,
  and test fixtures were redacted without altering author attribution, commit
  emails, or patch `From:` / `Signed-off-by:` headers: private LAN/host IPs use
  `192.0.2.1` / `192.0.2.0/24`, private feed domain uses `example.invalid`,
  personal SSH/user identifiers use `router-admin@192.0.2.1` and `desktop-user`,
  and personal checkout/evidence paths use `/srv/openwrt` and
  `/srv/openwrt-validation/...`.

The five updated ignored `feeds/*` repositories were also merged locally
(`--no-ff`) and re-indexed with `./scripts/feeds update -i -a` and
`./scripts/feeds install -a`; `feeds/routing` (`2ae1f6df7b`),
`feeds/taskplan` (`8417a64b29`), and `feeds/telephony` (`5dbc0e9150`) had zero
incoming commits:

- `feeds/luci`: `7397e28c07` (merged `gitlab/master` `4e067c2e51`)
- `feeds/packages`: `a10dac727e` (merged `gitlab/master` `5b68c6ddf0`)
- `feeds/passwall_luci`: `32baa9dc3d` (merged `gitlab/main` `21a1b9fc2e`)
- `feeds/passwall_packages`: `cd8f6892ae` (merged `gitlab/main` `30edd775ab`)
- `feeds/video`: `802a5e30e0` (merged `gitlab/master` `d04640d5c8`)

| Check | Result |
| --- | --- |
| Author attribution | All 43 replayed commits on `sync/gitlab-20261124` match original author names, emails, dates, and `GitLab-source:` trailers (`0` mismatches) |
| Personal marker scan | Scanned all 43 replayed commit messages and added lines plus incoming feed diffs; `0` leaked personal IPs, domains, paths, or accounts (`From:`/`Signed-off-by:`/author emails preserved per policy) |
| Content parity | All 404 modified files in `main..sync/gitlab-20261124` match sanitized `gitlab/main`; diffs vs `gitlab/main` (`175` files) are confined to pre-existing public deltas plus newly sanitized docs, `.gitmodules`, and test fixtures |
| Whitespace (`git diff --check`) | Passed on `main..sync/gitlab-20261124` (`0` issues) |
| `scripts/feeds update -i -a` & `install -a` | Exited 0; feed indexes regenerated cleanly |
| Host Python test suite (`scripts/tests/test-*.py`, excluding VM/CLI harnesses) | 59/73 suites passed (including `test-desktop-setup.py`, `test-desktop-sessions.py`, `test-luci-desktop.py`, and `test-sunshine-gnome.py`); 14 suites failed due to pre-existing host/target environment prerequisites: 7 require `python3-pyelftools` (`elftools`) for `scripts/elf-type-abi.py` (`test-allocate-rebuild-releases.py`, `test-apk-rebuild-phase2.py`, `test-build-and-publish.py`, `test-diagnose-apk-rebuild.py`, `test-elf-abi.py`, `test-lan-apk-publisher.py`, `test-scheduled-maintenance.py`), 1 expects built installer ISO/APK catalog artifacts (`test-installer-components.py`), 1 reflects upstream `xdg-desktop-portal` release 5 vs GCC 15 rebuild ledger entry 6 (`test-systemd-router-decoupling.py`), and 5 are pre-existing host/target environment checks (`test-apk-source-versions.py`, `test-apk-transaction-journal.py`, `test-boot-readiness.py`, `test-irqbalance-netdev-cpus.py`, `test-rtkit-desktop.py`) |
| Node.js LuCI view suites (`scripts/tests/test-luci-*.js`: all 10 suites) | All 10 suites passed (including `test-luci-desktop-view.js`) |
| `scripts/tests/test-alternatives.sh` | Passed |

Scope: local source synchronization across `openwrt-systemd-host` and the
active `feeds/*` repositories plus host unit checks only. No firmware/package
build, VM execution, physical-router modification, APK feed publication, or
remote push was performed.
