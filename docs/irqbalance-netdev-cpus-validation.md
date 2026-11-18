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

At source-patch completion, no router package installation, service restart, UCI change, feed publication or reboot had been performed; the separately authorized publication/deployment below supersedes that status. No VM or new throughput/latency benchmark was run: this task requests a source patch, and native protected-daemon execution plus synthetic placement/activation tests validate the new functionality without deploying it. Actual router effective affinities, reboot/hotplug behavior, kernel-managed interrupt restrictions and performance require a separately authorized deployment and device check. The earlier LAN RPS benchmark is not evidence of this IRQ patch's performance.

## Publication preparation — 2026-11-15

The first private r3 artifact conflicted with an existing published identity because the recipe r2 was mapped to r3 by `configs/apk-elf-rebuilds.mk`. The recipe is now r4; the original published r3 APK was restored byte-for-byte in local outputs. No published r3 bytes or migration entries were changed. The r4 package was rebuilt and the complete source/CLI/UCI/native sandbox suite passed again.

## Published and installed on the physical router — 2026-11-15

User explicitly authorized commit, publication and router installation.

- Main integration commit: `6e6483a05c`; packages feed head: `ab479830befa928f964afd49e9433957c88971ee`.
- Coordinated dry-run and formal publication both passed signature/immutability, ELF/dependency and reachable-router upgrade checks. The simulated change was only `irqbalance 1.9.5-r3 → 1.9.5-r4`.
- Published userspace snapshot: `/srv/openwrt-feeds/public/snapshots/20261114T160445.978679Z`. Kernel channel unchanged, generation `7.3.4-63-openwrt`.
- Router refreshed signed indexes, independently simulated the targeted transaction, then installed r4 using `apk upgrade irqbalance`. No trust/signature or dependency checks were bypassed. APK world was byte-identical afterwards.
- UCI transaction `b0e0cab5660d43e2afdb6e7ccdf351b2` guarded the installation/configuration. Added `netdev_cpus` list entries `eth0:0-3,8-11` and `eth1:0-3,8-11`, committed and restarted through `/etc/init.d/irqbalance`. Validation passed and the transaction was confirmed; history head is 64, no drift or pending rollback.
- Running command: `/usr/sbin/irqbalance -f -c 2 -t 10 --netdev-cpus eth0:0-3,8-11 --netdev-cpus eth1:0-3,8-11`. Existing boot enablement remains in place.
- Repeated observations after balance cycles and a final assertion found all ten eth0/eth1 IRQs' configured and effective CPU sets nonempty and contained in CPU 0–3,8–11. No global banned CPU list was added.

Final affinity snapshot (assignments remain dynamic):

| Device | Administrative IRQ | TxRx queue 0 | Queue 1 | Queue 2 | Queue 3 |
|---|---|---|---|---|---|
| eth0 | IRQ154 → CPU2 | IRQ155 → CPU2 | IRQ156 → CPU11 | IRQ157 → CPU9 | IRQ158 → CPU3 |
| eth1 | IRQ159 → CPU3 | IRQ160 → CPU3 | IRQ161 → CPU0 | IRQ162 → CPU8 | IRQ163 → CPU3 |

Unrelated devices remain unrestricted: observed NVMe IRQs on CPUs 7/5, xHCI on CPU7 and Wi-Fi on CPU5. This confirms the constraint is per matching network device rather than a global exclusion.

IPv4, IPv6, DNS and WireGuard-link health checks passed; the build host reached the router and guest VM without loss in the connectivity probes. CAKE remains 130 Mbit/s, LAN/WAN RPS remains f0f, VM cputune and boot ID are unchanged. No reboot, hotplug event or new throughput/latency benchmark was performed; the previous RPS benchmark does not measure the performance of this new IRQ policy.

Router backup and private evidence: `/root/irqbalance-netdev-deploy-20261115-000253/` contains the signature-verified old r3 APK, old config/init/binary/world, before/after state and targeted transaction plans. Policy rollback can remove the two `netdev_cpus` entries and restart irqbalance under a new confirmed UCI-history transaction; the patched daemon's no-rule behavior is unchanged.
