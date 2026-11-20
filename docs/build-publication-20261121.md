# Build and publication — 2026-11-21

The authorized `./scripts/build-and-publish.sh -j16` workflow completed
successfully and published **Linux `7.3.5-77-openwrt`** together with the
2026-11-21 upstream main/feed synchronization.

The first full-build attempt stopped at `libx264` before publication. A verbose
single-job `package/feeds/packages/libx264/compile` retry succeeded without any
source or configuration edit. The resumed full workflow reused generation 77
after its compiled-image/input checks and completed the build and publication.
No package identity was overwritten and no rebuild-ledger allocation was used.

## Published artifacts

- Userspace snapshot: `20261120T162445.831617Z`
- Userspace kernel/ABI identity: `7.3.5~5eaacd40bf4a752328abbcfbf2b75c1e-r1`
- Kernel snapshot: `1795191913699950743`
- Kernel generation: `7.3.5-77-openwrt`; manifest sequence 77, retaining three
  generations, with no cleanup warnings.
- `public/current` and `public/kernel-upgrades` resolve to these snapshots.
- The userspace snapshot contains 3209 packages across nine repositories,
  including retained artifacts. Its 280 changed-package entries are publication
  candidates, not a count of packages installed on the router.
- Notable userspace updates include LuCI base/translations, v2ray geodata and
  `base-files-1769.20~e7f788a9c1`; generation-77 kmods include mac80211 r16.

## Validation

The full build, coordinated signature/ELF/ucode/dependency checks,
immutable-identity checks, reachable-router baseline and full upgrade simulation
passed. The simulation returned 0 with no blockers and proposed 282 changes,
including installation of `linux-image-7.3.5-77-openwrt` and its headers. This
is a solver preview, not an installation or runtime result.

HTTP retrieval of all nine current repository indexes, the kernel manifest and
the kernel index matches the published files byte for byte (11 checks).
The only working `.config` value changed by the build is
`CONFIG_OPENWRT_KERNEL_SEQUENCE=76` to `77`. Every pre-sync repository HEAD
remains an ancestor; original local source states and untracked content are
preserved.

| Local artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `openwrt-x86-64-generic-squashfs-combined-efi.img.gz` | 970311239 | `540179f190eb22fb4028321210d26e83b144940727f3c1effd99475a02298e78` |
| `openwrt-x86-64-generic-squashfs-rootfs.img.gz` | 959483447 | `8db386b8abb798d39fb6483d7164f33c5f27d68ab339ca2f5a544a0ca7c9cfbe` |
| `openwrt-x86-64-generic-installer.iso` | 1099046912 | `615e457b7f7f1b23353b994752474b4d286a4d8f2c64b45f26efa5a2c03322f1` |

Artifacts are under `bin/systemd/targets/x86/64-glibc/`. Evidence is in
`.git/build-publish-20261120T161138Z/`: the complete result and build log,
initial-failure and libx264-retry logs, summary, HTTP verification, image hashes
and final preservation verification.

## Runtime boundary

No VM was run solely for publication. These are compatible upstream fixes and
routine package/generation updates within existing functionality, not a new
feature requiring a new runtime profile. Source checks, a complete package/image
build and the coordinated router preflight were used.

No package was installed on the physical router, and no router service or
desktop session was restarted. No firmware was flashed, no reboot occurred and
no Git push was performed. Publication does not establish physical boot,
wireless/AP-VLAN behavior or desktop/client acceptance.
