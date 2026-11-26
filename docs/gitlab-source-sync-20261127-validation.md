# GitLab source synchronization validation (2026-11-27)

Integrated GitLab main updates after `a166bed5c260c654111ecde7e8379bb08d863c1a`
through `d92751db7133708985db2edabeb97a138684c6e3` onto the public tree on
branch `sync/gitlab-20261127`. All 7 incoming non-merge commits were replayed
with individual provenance records (`GitLab-source:` trailers). Original author
names, email addresses, and dates were preserved and verified against GitLab.
Private GitLab history is not a merge parent.

Major changes integrated include removing `procd`'s hotplug file queue patch
(`150-systemd-udev-hotplug-queue.patch`, restoring direct `openwrt-udev-forward`
→ `procd.udev event` ubus forwarding in `procd` r12), retiring per-feature feed
manifests and incremental `patches/feeds/0001..0055` patches in favor of the
cumulative mirror snapshots, retiring `configs/mainline-kernel-patches.json` and
condensing `docs/mainline-kernel-patch-review.md`, dropping unused
`nft_fullcone` expression patches from `libnftnl`/`nftables`/`firewall4` while
retaining `brcm` fullcone mode, simplifying APK kernel generation patches and
updating policy tests, refining `systemd` udev sound rules, `procd` netlink
uevent validation (`110-netlink-uevent-validate.patch`), `dnsmasq` audit
patches, `rpcd` patch numbering, and `busybox` `cron.service`, and dropping
retired desktop/virtualization workarounds (`freerdp`, `pipewire`, `libvirt`,
`virt-manager`, `openwrt-desktop-plasma`) with expanded `test-desktop-sessions.py`
and `test-auxiliary-systemd.py` coverage.

Merge and conflict resolutions against public-only tree differences:

- `CLAUDE.md` (`970c65ca99`): kept public-excluded `CLAUDE.md` deleted.
- `patches/feeds/0001..0031` (`538f6511db`) and
  `package/network/config/firewall4/patches/008-firewall4-probe-ipv6-fullcone-support.patch`
  (`732515d9c9`): resolved modify/delete conflicts by deleting the retired
  patches.
- `docs/mainline-kernel-patch-review.md` (`faeff7a4bb`): adopted the condensed
  18-line replacement from `faeff7a4bb` (contains no personal markers).
- Personal identifiers in commit `970c65ca99` (commit message,
  `docs/systemd-udev-hotplug-migration-plan.md`, and
  `docs/systemd-udev-hotplug-migration-validation.md`) were redacted without
  altering author attribution or commit emails: private LAN router IP
  `192.168.2.1` → `192.0.2.1`, personal desktop username → `desktop-user`,
  personal VM name → `guest-vm`, and personal router boot ID → `<redacted>`.

The single updated ignored `feeds/*` repository was also merged locally
(`--no-ff`) and re-indexed with `./scripts/feeds update -i -a` and
`./scripts/feeds install -a`; `feeds/luci` (`2811b29717`), `feeds/packages`
(`5d348ca01`), `feeds/passwall_luci` (`32baa9dc`), `feeds/passwall_packages`
(`cd8f689`), `feeds/routing` (`2ae1f6d`), `feeds/taskplan` (`8417a64`), and
`feeds/telephony` (`5dbc0e9`) had zero incoming commits:

- `feeds/video`: `4d87797` (merged `gitlab/master` `91fb9d4`, reverting retired
  local `weston` desktop patches to upstream)

| Check | Result |
| --- | --- |
| Author attribution | All 7 replayed commits on `sync/gitlab-20261127` match original author names, emails, dates, and `GitLab-source:` trailers (`0` mismatches) |
| Personal marker scan | Scanned all 7 replayed commit messages and added lines plus incoming `feeds/video` diff; `0` leaked personal IPs, paths, accounts, VM names, or boot IDs (author names and emails preserved per policy) |
| Content parity | All 199 modified files in `main..sync/gitlab-20261127` match sanitized `gitlab/main`; the 8 differing touched files and 163 total differing files vs `gitlab/main` are confined to pre-existing public deltas plus newly sanitized docs |
| Whitespace (`git diff --check`) | Passed on `main..sync/gitlab-20261127` (`0` issues) |
| `scripts/feeds update -i -a` & `install -a` | Exited 0; feed indexes regenerated cleanly |
| `scripts/audit-hotplug-merge.py` | Passed; 14/14 hotplug JSON classifications verified |
| Host test suite (`python3 scripts/tests/run-host-tests.py`, 84 scripts) | 48 passed, 8 passed with skips, 14 skipped, 14 failed due to the same pre-existing unbuilt-tree / host-environment prerequisites (`elftools`, `staging_dir/host/bin/apk`, `staging_dir/hostpkg/bin/ucode`, cross-compiler toolchain, and `test-irqbalance-netdev-cpus.py`). All newly updated runnable host tests (`test-auxiliary-systemd.py`, `test-systemd-udev-boundary.py`, `test-udev-hotplug-migration.py`, `test-desktop-sessions.py`) passed |

Scope: local source synchronization across `openwrt-systemd-host` and the
active `feeds/*` repositories plus host unit checks only. No firmware/package
build, VM execution, physical-router modification, APK feed publication, or
remote push was performed.
