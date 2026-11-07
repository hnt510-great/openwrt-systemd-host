# Full image build, VM validation and publication, 2026-11-07

Built the x86/64 glibc native-systemd GNOME firmware after the 2026-11-07
main/feed synchronization (see the [patch review](mainline-kernel-patch-review.md)).
It includes Linux 7.3.3, the ported `hack-7.3/904-debloat_dma_buf.patch`, procd
r7, busybox r12, mesa r9, openssh 10.6p2, fuse3 3.18.3, fastfetch 2.71.0 and
luci-theme-argon 3.1.3. The build used
`scripts/build-and-publish.py build-only -j8 V=s` and exited successfully with
reserved kernel generation 55. `.config` was normalized with `make defconfig`
first; it gained only upstream's BusyBox history defaults.

## Exact artifact

- Release: `7.3.3-55-openwrt`, revision `r38178+332-7e8bfcfe76`.
- EFI image: `openwrt-x86-64-generic-squashfs-combined-efi.img.gz` (750016615 bytes).
- SHA256: `0fa46b1442a8a620c1f026eaf27903ace7e4475cbd8236078611002450f990cc`.

## VM acceptance

The exact compressed image was booted by `scripts/test-image-network.py` as a
router plus LAN client pair on isolated QEMU networks.

| Check | Result |
| --- | --- |
| Native systemd init | Passed |
| Router services | Passed |
| WAN DHCP, LAN DHCP | Passed |
| DNS | Passed |
| Routing/NAT | Passed |
| LuCI HTTP and authentication | Passed |
| ubus board | Passed |

The scope is the basic network gate only (9/9). Desktop, libvirt, SPICE, RDP,
PPPoE, physical NICs and physical-router acceptance were not exercised.

## Publication

- Userspace: `/srv/openwrt-feeds/public/snapshots/20261107T050246.739088Z`;
  ABI tree `7.3.3~4bced1b62a15039b17cdd322f176398f-r1`, 1529 packages.
- Kernel: `/srv/openwrt-feeds/public/kernel-snapshots/1794027805182552439`;
  34 packages, 3 image generations.
- The router upgrade preflight (both solver simulations) passed before
  promotion. Receipt `upgrade-receipts/1794027813268991540.json`. Nothing was
  installed on the router and it was not rebooted.

Evidence: `bin/validation/sync-20261107/` (build and publication logs, image,
VM receipt).
