# irqbalance per-netdev CPU pools — validation

Date: 2026-11-14. Checkout: `/srv/openwrt` on the build host. Package source: irqbalance 1.9.5.

## Source/package identity

- Packages feed base: `9c6a80d3c9f0b3e48c4c33e712532d92cdd3c11e`.
- Local feature commit: `ab479830befa928f964afd49e9433957c88971ee` (`irqbalance: support per-netdev CPU pools`). No push performed.
- Source patch: `feeds/packages/utils/irqbalance/patches/030-netdev-cpu-pools.patch`, regenerated through `make package/feeds/packages/irqbalance/refresh`.
- Portable feed mirror: `patches/feeds/0038-packages-irqbalance-netdev-cpus.patch`; reconstruction manifest: `configs/irqbalance-netdev-cpus-feeds.json`.
- Recipe `PKG_RELEASE` increments 1 → 4, avoiding the reserved r1/r2 → r3 ELF migration mappings. The native build's effective artifact is `bin/systemd/packages/x86_64/packages/irqbalance-1.9.5-r4.apk`.
- APK SHA-256: `c07af6848ef2d0d57c21454fc06741c52afd0c1143ddd5916c56a2266e0869f4`.
- Working `.config` is unchanged, still byte-identical to the tracked full desktop snapshot; SHA-256 `e054b44cf39ff2bd791c2071e8bdff55682ef4407faa71eaff1bc9486465822d`.

## Checks passed

1. Pristine upstream source plus all three package patches applies with `patch --fuzz=0`; every file changed by patch 030 exactly matches the prepared source.
2. Full OpenWrt package compile: `make package/feeds/packages/irqbalance/compile -j4 V=s`. New source is built and linked; APK packaging and existing ABI checks pass.
3. `python3 scripts/tests/test-irqbalance-netdev-cpus.py --native` passes:
   - CPU-list errors (empty, malformed separators, reversed/out-of-range) rejected; wildcard/exact/overlapping rules, shared-device intersections and CPU IDs above 64 through 4095 covered.
   - Unmatched/default and explicitly banned IRQs retain their existing behavior.
   - Actual activation code writes only the intersection of pool, online CPUs and global permissions; repeated application is idempotent; empty-pool state does not write an invalid affinity and recovers when CPUs return.
   - Actual placement code spreads two synthetic IRQs between permitted CPUs while an unrelated IRQ still selects a CPU outside that pool.
   - Built-daemon CLI accepts repeated rules and rejects malformed rules before startup. Mocked procd verifies UCI wildcard entries stay separate, quoted arguments.
   - Built daemon executes against real PCI sysfs in a private user/mount namespace. `/proc/irq` is mounted read-only and a test interposer captures both fopen/fopen64 affinity writes. With `enp42s0:0,2`, its IRQ 74 is assigned mask `00000004` (CPU 2); unrelated IRQ writes include CPUs outside the pool. No host IRQ affinity was changed by this test.
4. `sh -n` on the init script; recipe/init/config whitespace checks pass. Patch payload context whitespace is excluded from Git's whitespace check, as it is upstream diff data.
5. `scripts/checkpatch.pl --no-tree --no-signoff --ignore NR_CPUS .../030-netdev-cpu-pools.patch`: zero errors/warnings. Signoff is not asserted for this local patch; the kernel-only NR_CPUS advice is inapplicable because this userspace bitmap implementation explicitly bounds IDs by that constant.

## Validation boundary

No router package installation, service restart, UCI change, feed publication or reboot was performed. No VM or new throughput/latency benchmark was run: this task requests a source patch, and native protected-daemon execution plus synthetic placement/activation tests validate the new functionality without deploying it. Actual router effective affinities, reboot/hotplug behavior, kernel-managed interrupt restrictions and performance require a separately authorized deployment and device check. The earlier LAN RPS benchmark is not evidence of this IRQ patch's performance.

## Publication preparation — 2026-11-15

The first private r3 artifact conflicted with an existing published identity because the recipe r2 was mapped to r3 by `configs/apk-elf-rebuilds.mk`. The recipe is now r4; the original published r3 APK was restored byte-for-byte in local outputs. No published r3 bytes or migration entries were changed. The r4 package was rebuilt and the complete source/CLI/UCI/native sandbox suite passed again.
