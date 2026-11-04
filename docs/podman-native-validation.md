# Native OverlayFS and pasta validation, 2026-10-21

## Build and packages

The x86_64/glibc native-systemd package builds, full image build and strict
Kconfig recursion checks passed. Shell syntax checks, feed patch reverse-apply
checks and source/payload hash checks passed. Existing unrelated work was
preserved; the active configuration gained passt without changing existing
package selections. No commits were performed. The three tested APKs were published to the signed
LAN feeds; see the publication record below.

| Package | Tested version |
| --- | --- |
| podman | 5.8.4-r6 |
| openwrt-podman-rootless | 3 |
| passt | 2026.10.02-r1 |

Passt is pinned to upstream tag `2026_10_02.cba3570`; the source archive SHA256
is `aa75616cc43925f0bd6c05bcfbbaecd77397c03d7bd23591b34ef535be5dfcdc`.
Its package contains the generic and runtime-selected AVX2 binaries, pasta
entry points, and upstream seccomp isolation. The cross-build patch supplies
the target's 4096-byte page size instead of querying host getconf.

Accepted image:
`bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz`

SHA256:
`8de0ccb5f461ac4855d0e9255f7324d678f25de511247d5cb93f2d53687e73dd`

## Disposable VM proof

The exact accepted image was booted with a disposable NVMe ext4 extroot.
Only the VM WAN was adapted from PPPoE to DHCP. A private copy of the
router's Passwall configuration enabled real TPROXY tests inside the VM.

- Native ext4-backed OverlayFS, actual kernel overlay container mounts,
  subordinate UID/GID mappings, ownership changes, DNS and HTTPS passed.
- Published TCP/UDP echo and local IPv6 TCP/UDP echo passed. External IPv6
  was unavailable on the VM's QEMU user network, so Internet IPv6 was verified
  separately on the physical router.
- Pasta worked with point-to-point IPv4 `/32` addressing and multiple host
  interfaces. Existing TPROXY and UDP/443 rejection counters advanced.
- Firewall/Passwall/DHCP config hashes and normalized nftables rule structure
  stayed unchanged. Normalization excludes counters, handles and set elements.
- New account enrollment, repeated enrollment and preservation of a populated
  old store passed. Managed TUN ACL revocation preserved an unrelated ACL.
- After reboot, the native container restarted without login; pasta, kernel
  overlay, the user API/timers and the per-user TUN ACL were active.

Pasta drops supplementary groups during isolation. The original `root:podman`
0660 device policy therefore needed an additional ACL for each enrolled UID.
The boot/setup helper maintains those ACLs without weakening pasta's sandbox
or granting access to all users. No kernel configuration change was needed.

Three-run medians with the same cached Alpine image:

| VM workload | Previous FUSE/slirp | Native overlay/pasta |
| --- | ---: | ---: |
| 256 MiB write, fsync, 3000 small files and removal | 2.282 s | 0.591 s |
| Published TCP echo payload throughput | 3.01 MiB/s | 86.94 MiB/s |

These are controlled VM workload results, not Internet throughput guarantees.

## Physical router

The router verified all three signed APKs. Offline simulation and installation
changed exactly those three packages. Installed Podman/passt binary hashes and
rootless helper hashes match the tested payloads.

A pasta canary passed over the real PPPoE connection with both IPv4 and IPv6
before stopping application services. The services were then recreated from
their existing image IDs with their original bind-mounted application data.
Their Quadlets now explicitly select `Network=pasta`.

- All three applications use actual kernel overlay root mounts with graphroot
  `/overlay/containers/32769/storage`; native overlay diff is enabled.
- Aria2, AriaNg and SearXNG are active with their original published addresses
  and ports. AriaNg and SearXNG health checks returned HTTP 200; ports 6800 and
  6888 accepted TCP connections. A temporary published UDP echo test passed.
- DNS/HTTPS and IPv4/IPv6 requests passed and matched the previous proxy exit
  addresses. TPROXY interception and the existing UDP/443 rejection policy
  were also checked through rule counters.
- No rootless fuse-overlayfs or slirp4netns helpers remain running.
- Boot ID and running kernel remain unchanged:
  `6.18.55-owrt-d7ef8dc7f60b053d6a57a4f73b5dad2b-r1-g21`.
- Firewall, Passwall, network, DHCP, subuid and subgid hashes are unchanged.
  The normalized full nftables structure is unchanged; procd and router
  services remain active. No firewall/Passwall reload, flash or router reboot
  was performed. Physical reboot behavior remains untested.

The old store remains inactive at
`/home/builder/.local/share/containers/storage`; existing containers/internal
volumes were not migrated. The three application images and Alpine were
loaded into the fresh native store. No bind-mounted application data was
removed. Large temporary installation archives were removed from router RAM.
Rollback Quadlets, the native storage config and a user rollback script are
retained on the router under
`~/.local/state/podman-native-20261021-gnZ5Z6/`.

## Evidence

Private build logs, package/source hashes, image receipt, serial logs,
benchmarks, before/after nftables snapshots, config hashes and deployment
checks are retained outside the checkout at:

`/srv/openwrt-validation/podman-native-validation-20261021-ekuri4x2/`

Both task VMs were stopped. Existing host VMs were left alone.

## Feed publication

Published snapshot `20261021T090639.281582Z` contains the exact tested APKs:
`passt-2026.10.02-r1`, `openwrt-podman-rootless-3` and `podman-5.8.4-r6`.
An isolated source tree restricted the dry run and publication to these three
packages. The signed base, custom and packages indexes were refreshed; all
three APK hashes were verified over HTTP and the router's `apk update` passed.

The build ABI is `6.18.55~d7ef8dc7f60b053d6a57a4f73b5dad2b-r1`, matching
the existing kernel channel. Generation g22 was already published. No kernel
publication was needed, and the kernel manifest hash is unchanged. No package
upgrade or router reboot was performed during publication. Publication receipts
and the router index-refresh log are retained under `publication/` in the
evidence directory above.
