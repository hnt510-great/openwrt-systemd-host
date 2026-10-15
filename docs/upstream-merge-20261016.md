# Upstream merge review, 2026-10-16

Updated the build checkout only. No firmware/kernel compilation, new APK
publication, physical installation, service restart or reboot was performed.
The current installed/published G7 artifacts remain separate from this source
update. Local commits were retained by merge, never reset or rebase.

## Local functional commits

The requested changes were committed before fetching upstream. Main-tree and
packages-feed histories remain separate; personal configuration, backups,
nested theme checkout state and Python caches were excluded.

| Repository | Commit | Change |
| --- | --- | --- |
| main | `f440e0132d` | kernel: add protected parallel APK kernel upgrades |
| main | `43e5a87d3f` | build: publish immutable kernels with input-based generations |
| main | `e597e51118` | merge-usr: resolve relative alternative targets from link parents |
| main | `d78727c7b3` | distrobox: add rootless distribution containers to the desktop |
| packages | `7ae9607e42` | openssh: install ssh-copy-id with client utilities |
| packages | `9265ca3740` | net-tools: add standalone ifconfig package |
| packages | `bb467e3a50` | procps-ng: expose pidof as a standalone package |
| packages | `07cec2d2d2` | ncat: retain single-address receive-only listeners |
| main | `9962ad5cbf` | desktop: select common command-line utilities |
| main | `218a222acb` | utilities: prefer standalone commands with BusyBox recovery fallbacks |

The packages-feed source diff and its original base/commits are recorded in
[cli-utils-feeds.json](../configs/cli-utils-feeds.json) and its linked patch.
The later upstream merge does not erase that provenance.

## Merge results

| Repository | Incoming commits | Result |
| --- | --- | --- |
| main | 44 | Merged origin/main through 45b61911a6f; merge adeac63608 |
| luci | 26 | Merged origin/master; merge 816a3147 |
| packages | 17 | Merged origin/master; merge d7887ab |
| passwall_luci | 7 | Fast-forwarded through b15b5799 |
| passwall_packages, routing, taskplan, telephony, video | 0 | Existing local commits retained |

Every configured Git feed contains its fetched upstream tip with zero commits
behind. Existing local ahead commits are intentional. There were no unresolved
conflicts. The only main-tree path changed on both sides was sysupgrade; its
automatic merge retained both upstream partition-option exports and local
home-directory backup metadata/systemd recovery guards.

Recreated all nine feed indexes (including src-link custom), installed feed
links and refreshed package metadata. All indexes are nonempty and there are
no broken links under package/feeds. The existing BMX7 missing-dependency
warnings remain; indexing/install/metadata commands exited successfully.

## Changes related to local features

- x86 now uses the shared legacy-sdcard helper. The upstream helper refuses an
  implicit whole-disk write when changed layouts would erase extra partitions;
  explicit sysupgrade -p retains its documented erase semantics. Partx becomes
  a legacy-sdcard dependency. Native-systemd flashing still requires procd
  recovery. APK kernel upgrades remain independent of this flashing path.
- Kernel filesystem package requests drop obsolete Kconfig symbols. With the
  existing selections this removes CONFIG_AUTOFS4_FS=m from config.set and
  changes OpenWrt's configuration ABI hash, despite unchanged Linux sources.
- The external NTFS module gains integrity/compression fixes. The current
  profile selects in-tree kmod-fs-ntfs3, not this external kmod-fs-ntfs package.
- linux-firmware updates to 20260916 and host libdeflate to 1.26. Firmware changes
  can affect supported GPU/NIC devices on a future image/upgrade; retained kernel
  generations keep their frozen firmware. Libdeflate is a relevant build input,
  so it also justifies a new generation even independently of the ABI change.
- LuCI eagerly computes package version strings to avoid repeated git queries;
  its upstream change states metadata is unchanged. Both custom LuCI packages
  and local video/container/native-tool feed commits remain in history.
- PassWall changes SmartDNS/nftset handling and adds Xray MASQUE/WARP UI support.
  Those changes require later runtime acceptance if built/deployed. No running
  router configuration or package was changed by this update.

## Kernel ABI calculation

Linux remains 6.18.55 with LINUX_RELEASE=1. Using the unchanged working .config,
fresh package metadata, the actual kconfig.pl merge and Kernel/SetNoInitramfs
rules, then the same sorted enabled-option MD5 as Kernel/Configure/Default:

| Role | Exact ABI |
| --- | --- |
| Existing compiled/physical G7 | 6.18.55~f10b60a7da5b97b579b974213f7b729c-r1 |
| Next build from merged sources/current configuration | 6.18.55~525c049ccf38fc1e86441c4482731299-r1 |

The freshly reconstructed target configuration matched the existing target
configuration byte-for-byte. The only enabled-option difference in config.set
was removal of CONFIG_AUTOFS4_FS=m. Recalculating the old config.set reproduced
its existing .vermagic exactly. This is a source/config calculation, not a
claim that the new kernel has already compiled or booted.

The read-only build-input preview detects changed relevant inputs. With the
inspected artifacts/channel, the next unused publication sequence is G8. The
normal combined build reserves it and rebuilds the matching image/modules;
no sequence/cache/config was changed by this review. New modules must not be
forced onto the old running kernel.

## Validation and preservation

After merge, 29 kernel/package, 39 build/publication, 13 LAN-publisher, nine
signed chroot APK-policy and eight merged-/usr tests passed (98 total). Four
isolated legacy-sdcard mode checks passed for preserved extra partitions,
refusal of changed layouts with extra partitions, explicit full-image erase
selection and normal layout changes. They mock device access and write no disk.
Affected shell syntax and git diff checks passed. These are bounded source
checks; no full rebuilt-image or new physical acceptance is claimed.

All nine pre-update repository tips remain ancestors of their resulting HEADs;
stashes and unrelated index state were preserved. All 39 captured working
configuration/overlay/personal-file hashes remain unchanged. Pre-update backup
branches exist in each repository. Configuration, overlay copies, commit lists,
merge review, test logs and the exact ABI inputs/results are retained privately
under:

/srv/openwrt-validation/upstream-update-20261016T023630
