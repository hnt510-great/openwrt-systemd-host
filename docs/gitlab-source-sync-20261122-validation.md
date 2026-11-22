# GitLab source synchronization validation (2026-11-22)

Integrated GitLab main updates after `7d58639eb0f062584fb656e05db26f2e7cd1e223`
through `a25660f3d3ca795fbc05fcc57d793330b0f3ef4a` onto the public tree on
branch `sync/gitlab-20261122`. All 115 non-merge commits (61 OpenWrt upstream
commits across five upstream merges `5009212efb`, `49f4f53f74`, `3ced84a7dc`,
`47d93490b2`, and `8a4732c9cb`, plus 54 local integration commits) and the
`package/kernel/linux/modules/netfilter.mk` conflict resolution from
`47d93490b2` have individual provenance records (`GitLab-source:` trailers).
Original author names, email addresses, dates, and `Signed-off-by` /
`Co-Authored-By` / `Suggested-by` / `Tested-by` trailers were preserved and
verified against GitLab. Private GitLab history is not a merge parent.

Major changes integrated include the standalone pure-router systemd
configuration (`configs/x86-64-systemd-router.config`, composable feature
fragments, `xdg-desktop-portal` / `virt-manager` decoupling), signed offline
optional component installation for `openwrt-installer` (`openwrt-desktop-core`
/ `openwrt-desktop-rdp` split and `--no-autostart`), x86/64 security hardening
and desktop/VM kernel features, GCC 15.3.0 toolchain switch and build fixes,
mainline Linux 6.18.64 / Realtek PHY hwmon / AMDGPU frame-size backports,
accelerated x86/64 rolling image packaging (LZ4 squashfs and commit-derived
`base-files` identity), Flatpak `flatpak-system-helper` with polkit `sudo`
group authorization, rolling package publication workflow, Qt6 on-device
development packages and optional KF6/Konsole terminal stack, fail-fast
transactional parallel build/staging improvements, evidence-based APK rebuild
diagnosis (`elf-type-abi.py`, per-package pack-keys, guarded cold rebuilds),
and upstream target/package updates (`glibc` 2.44 HEAD, `netfilter`
`kmod-nf-xtables` split, `odhcpd`, `hostapd`, `gettext-full`, `realtek`,
`mediatek`, `qualcommax`, `starfive`, `ramips`, `ipq40xx`, `qualcommbe`).

Merge and conflict resolutions against public-only tree differences:

- `docs/virt-manager.md` (`a5650a322c`): merged the `virt-manager` `5.1.0-r5`
  decoupling and headless virtualization note into the condensed public guide.
- `package/custom/openwrt-desktop/files/desktop-setup` (`fb06f73a6a`): merged
  `--no-autostart` with the public `--keyring-password-stdin` option.
- `docs/flatpak.md` (`7fd1fa261c`): adopted the updated GNOME +
  `flatpak-system-helper` documentation.
- `package/kernel/linux/modules/netfilter.mk` (`47d93490b2`): applied the exact
  `KernelPackage/iptables/description` conflict resolution from GitLab merge
  `47d93490b2`.
- `package/custom/luci-theme-argon` (`a39ad675a6`): kept the public submodule
  gitlink at `9e263d988b7be4d619442f297f4105871e12808` because
  `f5c74d235d3f778c728e8a9a5d4e47e8a657e408` is not present on the public
  GitHub remote.
- Personal identifiers in newly added/modified documentation and VM test
  fixtures were redacted without altering author attribution, commit emails,
  or patch `From:` / `Signed-off-by:` headers: private LAN/host IPs use
  `192.0.2.1`, personal SSH/user identifiers use `router-admin@192.0.2.1`,
  `Authenticating as: desktop-user`, and `! id example-user;`, and personal
  checkout/evidence paths use `/srv/openwrt`,
  `/srv/openwrt-validation/openwrt-parallel-draft`, and
  `/srv/openwrt-validation/...`.

The five updated ignored `feeds/*` repositories were also merged locally
(`--no-ff`, preserving `feeds/packages/lang/python/python3/Makefile`) and
re-indexed with `./scripts/feeds update -i -a` and `./scripts/feeds install -a`;
`feeds/routing` (`2ae1f6df7b`), `feeds/taskplan` (`8417a64b29`), and
`feeds/telephony` (`5dbc0e9150`) had zero incoming commits:

- `feeds/luci`: `218b681356` (merged `gitlab/master` `9cedfb04ae`)
- `feeds/packages`: `912a72d9b0` (merged `gitlab/master` `a582a06b38`)
- `feeds/passwall_luci`: `c964c1efa9` (merged `gitlab/main` `787594fff7`)
- `feeds/passwall_packages`: `715dc63f29` (merged `gitlab/main` `7657c33f93`)
- `feeds/video`: `df1142e808` (merged `gitlab/master` `cc362b753b`)

| Check | Result |
| --- | --- |
| Author attribution | All 116 commits on `sync/gitlab-20261122` match original author names, emails, dates, and `GitLab-source:` trailers (`0` mismatches) |
| Personal marker scan | Scanned all 115 replayed commit messages and added lines plus incoming feed diffs; `0` leaked personal IPs, paths, or accounts (`From:`/`Signed-off-by:`/author emails preserved per policy) |
| Content parity | All 571 modified files in `main..sync/gitlab-20261122` match sanitized `gitlab/main`; diffs vs `gitlab/main` (`210` files) are confined to `197` pre-existing public deltas plus `12` newly sanitized docs and `scripts/tests/test-installer-components-vm.py` |
| Whitespace (`git diff --check`) | Passed on `main..sync/gitlab-20261122` (`0` issues) |
| `scripts/feeds update -i -a` & `install -a` | Exited 0; feed indexes regenerated cleanly |
| Host Python test suite (`scripts/tests/test-*.py`, excluding 8 VM/CLI harnesses) | 56 test suites passed (including `test-desktop-setup.py`); 15 suites failed due to host/target environment prerequisites: 7 require `python3-pyelftools` (`elftools`) for `scripts/elf-type-abi.py` (`test-allocate-rebuild-releases.py`, `test-apk-rebuild-phase2.py`, `test-build-and-publish.py`, `test-diagnose-apk-rebuild.py`, `test-elf-abi.py`, `test-lan-apk-publisher.py`, `test-scheduled-maintenance.py`), 1 expects built installer ISO/APK catalog artifacts (`test-installer-components.py`), 1 reflects upstream `xdg-desktop-portal` release 5 vs GCC 15 rebuild ledger entry 6 (`test-systemd-router-decoupling.py`), and 6 are pre-existing host/target environment checks (`test-apk-source-versions.py`, `test-apk-transaction-journal.py`, `test-boot-readiness.py`, `test-irqbalance-netdev-cpus.py`, `test-rtkit-desktop.py`, `test-sunshine-gnome.py`) |
| Node.js LuCI view suites (`scripts/tests/test-luci-*.js`: all 9 suites) | All 9 suites passed |
| `scripts/tests/test-alternatives.sh` | Passed |

Scope: local source synchronization across `openwrt-systemd-host` and the
active `feeds/*` repositories plus host unit checks only. No firmware/package
build, VM execution, physical-router modification, APK feed publication, or
remote push was performed.
