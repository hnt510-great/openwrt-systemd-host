# GitLab source synchronization validation (2026-11-26)

Integrated GitLab main updates after `fffc3fa9e996a77c480d366d278e0431ad15f591`
through `a166bed5c260c654111ecde7e8379bb08d863c1a` onto the public tree on
branch `sync/gitlab-20261126`. Of the 53 non-merge commits (31 OpenWrt upstream
commits across two upstream merges `ae58193e90` and `ebb5e3d72c`, plus 22 local
integration commits), 52 were replayed with individual provenance records
(`GitLab-source:` trailers), while `5fa9526a37` (`docs: scrub VLESS address
from daed-client-features-plan`) was skipped because the VLESS address had
already been redacted in the public tree. Original author names, email
addresses, dates, and `Signed-off-by` / `Co-Authored-By` trailers were
preserved and verified against GitLab. Private GitLab history is not a merge
parent.

Major changes integrated include desktop color emoji + remotes stop deadlock
fix + LuCI Sunshine capture selector, udev takeover for KVM/render/desktop/
audio/Sunshine device policy, bounded disconnect queue and crash quarantine for
the `procd` udev bridge (`r11`), `scripts/audit-hotplug-merge.py` and udev/
hotplug migration tests/docs, Qt 6.11.3 `qt6charts` and on-device PIE/CMake/
prefix/plugin fixes, custom package updates (`cargo-c-bin`, `firefox-esr-bin`,
`flatpak`, `gnome-remote-desktop`, `libgdm`, `file-roller` 44.8) and release
bumps (`ppp`, `xdg-desktop-portal`, `bzip2`, `native-libs-dev`), `needrestart`
`/proc/PID/fdinfo` sandbox generalization, consolidated desktop test fixtures
and the new host test runner (`scripts/tests/run-host-tests.py`), Plasma/Qt6
10-component ISO config fixes, build/publish/preflight/updater optimizations,
`kernelctl`/`uci-history`/`router-audit`/`daed`/`needrestart` hardening and
GRUB timeout inheritance, cumulative replayable feed mirror snapshots
(`configs/feed-mirrors-snapshot.json`, `patches/feeds/0056..0059`,
`scripts/audit-feed-mirrors.py`), and upstream target/package updates
(`realtek` RTL930x/RTL931x TBF/ETS qdisc offload & TP-Link TL-ST5008F v2.0,
`airoha` Gemtek XR1710G, `ppp`, `starfive`, `uboot-mediatek`, `qualcommax`,
`generic` 6.18 MxL862xx & `device_schedule_reprobe`, `bpf-headers`,
`dsl-vrx200-firmware-xdsl`, `loongarch64`, `bzip2`, `bcm27xx`, `dnsmasq` ubus
lease methods, `linux-firmware` 20261124).

Merge and conflict resolutions against public-only tree differences:

- `docs/daed-client-features-plan.md` (`5fa9526a37`): skipped commit because
  the VLESS address was already redacted in the public tree.
- `package/custom/luci-theme-argon` (`793bf52c03`): kept the public submodule
  gitlink at `9e263d988b7be4d619442f297f4105871e12808` because
  `c89a8f110ea19ae8d1365ed673d5bc59fe3b33ca` is not present on the public
  GitHub remote.
- `CLAUDE.md` (`885e2516b3`): kept public-excluded `CLAUDE.md` deleted.
- `package/network/services/dnsmasq/Makefile` (`5dddea8513`): adopted the
  upstream merge resolution (`PKG_RELEASE:=17`) from `ebb5e3d72c`.
- `scripts/tests/run-host-tests.py`: registered public-only
  `test-desktop-setup.py` and `test-luci-desktop-setup.js` so the host test
  inventory guard passes on the public tree.
- Personal identifiers in newly added/modified documentation
  (`docs/systemd-udev-hotplug-migration-validation.md`,
  `docs/systemd-udev-hotplug-migration-plan.md`,
  `docs/qt6-development-validation.md`) were redacted without altering author
  attribution, commit emails, or patch `From:` / `Signed-off-by:` headers:
  private LAN router IP `192.168.2.1` → `192.0.2.1`, personal desktop username
  → `desktop-user`, personal VM name → `guest-vm`, and personal router boot ID
  → `<redacted>`.

The three updated ignored `feeds/*` repositories were also merged locally
(`--no-ff`) and re-indexed with `./scripts/feeds update -i -a` and
`./scripts/feeds install -a`; `feeds/passwall_luci` (`32baa9dc`),
`feeds/passwall_packages` (`cd8f689`), `feeds/routing` (`2ae1f6d`),
`feeds/taskplan` (`8417a64`), and `feeds/telephony` (`5dbc0e9`) had zero
incoming commits:

- `feeds/luci`: `2811b29717` (merged `gitlab/master` `b4b9e07cc5`)
- `feeds/packages`: `5d348ca01` (merged `gitlab/master` `4a077958b`)
- `feeds/video`: `19f1bca` (merged `gitlab/master` `d86d1eb`)

| Check | Result |
| --- | --- |
| Author attribution | All 52 replayed commits on `sync/gitlab-20261126` match original author names, emails, dates, and `GitLab-source:` trailers (`0` mismatches) |
| Personal marker scan | Scanned all 52 replayed commit messages and added lines plus incoming feed diffs; `0` leaked personal IPs, domains, paths, accounts, VM names, or boot IDs (`From:`/`Signed-off-by:`/author emails preserved per policy) |
| Content parity | All 206 modified files in `main..sync/gitlab-20261126` match sanitized `gitlab/main`; diffs vs `gitlab/main` (`179` files) are confined to pre-existing public deltas plus newly sanitized docs and `run-host-tests.py` public inventory entries |
| Whitespace (`git diff --check`) | Passed on `main..sync/gitlab-20261126` (`0` issues) |
| `scripts/feeds update -i -a` & `install -a` | Exited 0; feed indexes regenerated cleanly |
| `scripts/audit-hotplug-merge.py` | Passed; 14/14 hotplug JSON classifications verified |
| Host test suite (`python3 scripts/tests/run-host-tests.py`, 84 scripts) | 47 passed, 9 passed with skips, 14 skipped, 14 failed due to pre-existing unbuilt-tree / host-environment prerequisites: 6 require `python3-pyelftools` (`elftools`), 1 requires `staging_dir/host/bin/apk` (`test-apk-source-versions.py`), 4 require `staging_dir/hostpkg/bin/ucode` (`test-luci-{journal,podman,qemu,uci-history}.py`), 2 require `staging_dir/toolchain-.../x86_64-openwrt-linux-gcc` (`test-needrestart.py`, `test-systemd-service-bridge.py`), and 1 is a pre-existing host prerequisite (`test-irqbalance-netdev-cpus.py`). All 10 Node.js LuCI view suites (including `test-luci-desktop-setup.js` and `test-luci-desktop-view.js`), `test-desktop-setup.py`, `test-desktop-sessions.py`, `test-udev-hotplug-migration.py`, and `test-alternatives.sh` passed |

Scope: local source synchronization across `openwrt-systemd-host` and the
active `feeds/*` repositories plus host unit checks only. No firmware/package
build, VM execution, physical-router modification, APK feed publication, or
remote push was performed.
