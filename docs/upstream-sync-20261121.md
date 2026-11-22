# Upstream synchronization — 2026-11-21

Merged OpenWrt through `e7f788a9c11d66c4ecc071b06e5c39686cebd8a6`
(five incoming commits) as `3ced84a7dc530b9c92b758f7dd9ce80d72c3a870`.
Independent feed merges incorporate three LuCI commits through `a7b9db4615`
as `1b0815bd09`, and three Passwall packages commits through `a880c9046f`
as `e424380`. The packages, video, telephony, routing, taskplan and Passwall
LuCI feeds were already current. All merges retain their previous local HEAD
as an ancestor; no reset, rebase, force update or push was used.

Backup refs `backup/pre-upstream-20261120T160042Z` cover all 11 repositories,
including the Argon submodule and retired Argon configuration checkout.
Preservation receipts, incoming inventories, logs, the isolated Kconfig copy,
kernel application output and final verification are under
`.git/pull-preserve/20261120T160042Z/`. The working `.config`, tracked desktop
snapshot, kernel metadata, stashes and original untracked content are preserved.

## Integration and custom recipes

- The main tree merges without conflicts. Its changes are a Realtek DSA source
  refactor for the Realtek target and an AP-VLAN TX fix in the separate
  mac80211 backports package (`PKG_RELEASE` 15 to 16). They do not alter the
  native Linux 7.3 patch stack or the local systemd/desktop integration.
- LuCI merges without conflicts: batman-advanced status support, Docker
  multiplexed log handling and translation updates. Local firewall, ttyd,
  status, needrestart and other views remain in the retained feed history.
- Passwall packages updates smartdns to 48.5 and v2ray-geoip/geosite to
  202611190019/202611192204 without conflicts.
- `./scripts/feeds update -a` completed all 188 registered custom-package
  checks: 147 current, 36 locally maintained and five intentional review
  entries. No eligible custom recipe update or Argon submodule update was
  available. The review entries remain the Flatpak prerelease, the parallel
  gcr3/GTK3 slots, Intel media-driver tag noise and the libibus date-like tag.
  Report: `logs/custom-package-updates/20261120T160142.664865Z/report.json`.

## Linux 6.18 to 7.3 review

`python3 scripts/update-mainline-kernel.py --check` reports Linux **7.3.5**
as current. The source archive SHA-256 remains
`8f293f83d54f0b7b9be56863ebc5e4ea79d73e530b4ae55c572be97ef39f0990`.
No kernel version or patch metadata was changed.

There are zero incoming changes under `target/linux/generic/` or
`target/linux/x86/` between the previous upstream baseline `8b34d6283fc5` and
`e7f788a9c1`. Consequently there are no new generic or x86 6.18 patches to
review or backport. The mac80211 fix belongs to its external backports source
package and was validated there rather than duplicated into the native kernel.

The complete **357-patch** Linux 7.3 stack applies to a fresh extraction of the
SHA-256-verified 7.3.5 archive plus generic/x86 overlays with `--fuzz=0`.
Every registered 7.3 port hash matches. The audit still shows the existing 60
source-hash differences from the previously reviewed 6.18.64/context updates
(including the earlier MediaTek 799 offset refresh), and the four previously
documented unregistered non-x86 patches: one MIPS module-layout hack and three
MediaTek WED fixes. None is new in this synchronization or requires an x86/64
backport here. The optional MAP-E finding remains outside this batch.

## Validation scope

- Feed update/install and package metadata regeneration pass. All nine feed
  indexes are nonempty and `package/feeds` has no broken generated links.
- Strict `conf --fatalrecursive --olddefconfig` passes on an isolated copy of
  `.config`. No selected option changes. Normalization removes only the stale
  unset `PACKAGE_qt5base-plugin-input-libinput` symbol left by the preceding
  video-feed update and reorders the unset `dhtd` entry. The working `.config`
  remains byte-identical (SHA-256
  `01ac3314b73415e42f91d1afa525cfe09bbc94fda4eaad2c04bea155605ca24a`).
- Mainline updater (20), kernel build inputs (7), custom updater (49), package
  metadata/Kconfig (4), ELF ABI (23) and ucode ABI (6) tests pass. The LuCI
  firewall full-cone and needrestart JavaScript tests also pass.
- mac80211, smartdns and v2ray-geodata source preparation passes, including
  source verification and the mac80211 patch stack.
- Merge whitespace checks pass. All 11 original repository HEADs remain
  ancestors, and before/after status and stash inventories match.

No full firmware or kernel generation was built, and no VM or physical-device
runtime test was needed for this source-only synchronization. No feed
publication, Git push, router installation, service restart or reboot occurred.
This report and the kernel-review index entry are committed together with the
publication follow-up.

## Authorized follow-up: build and publication

The subsequent `./scripts/build-and-publish.sh -j16` workflow published
`7.3.5-77-openwrt`, userspace snapshot `20261120T162445.831617Z` and kernel
snapshot `1795191913699950743`. The full router upgrade simulation passed with
no blockers, and all 11 HTTP publication checks match their local files.

The initial build stopped at `libx264` before publication; a verbose targeted
retry succeeded without edits, and the resumed full build reused generation 77.
No VM or physical installation/reboot was performed. See
[the publication record](build-publication-20261121.md) for artifact hashes,
validation details and evidence paths.
