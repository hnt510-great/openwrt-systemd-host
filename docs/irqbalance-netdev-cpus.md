# Per-network-device IRQ CPU pools

The local irqbalance 1.9.5 patch adds optional CPU pools for PCI network-device IRQs. Matching IRQs continue to use irqbalance's load-based placement within their pool. Unmatched devices retain the normal policy. There are no compiled-in interface names, IRQ numbers or VM CPU assignments.

## Configuration

The option is repeatable and takes an interface name/shell wildcard followed by a decimal Linux CPU list:

```sh
irqbalance -f --netdev-cpus 'eth0:0-3,8-11' --netdev-cpus 'eth1:0-3,8-11'
# A wildcard is also accepted; quote it to prevent shell expansion.
irqbalance -f --netdev-cpus 'enp*:0-3,8-11'
```

These are alternative invocations, not additional daemons to run alongside the existing service. Short option: `-N`.

The OpenWrt init script accepts a `netdev_cpus` UCI list:

```uci
config irqbalance 'irqbalance'
        option enabled '1'
        list netdev_cpus 'eth0:0-3,8-11'
        list netdev_cpus 'eth1:0-3,8-11'
```

The example pool corresponds to `f0f` on the current 12-thread router, excluding VM CPUs 4–7. It is configuration, not a firmware default. No rules are enabled by the package. Global `banned_cpulist` keeps its existing global meaning and is not needed to restrict just the two NICs.

Only use this configuration after installing the patched package. Changing router UCI over SSH must use the repository's `uci-history --json begin --timeout 300 --note 'configure netdev IRQ pools'` transaction, followed by service/connectivity validation and `uci-history --json confirm`. Restart via `/etc/init.d/irqbalance restart`; do not manipulate the procd-owned systemd instance directly.

## Semantics

- Match physical network interfaces under the PCI device's sysfs `net/` directory. This covers all MSI/MSI-X vectors, including administrative IRQs; it does not rely on action names such as `eth0-TxRx-0`.
- Multiple matching rules are intersected, including multiple interfaces/devices sharing the same IRQ. Rules do not expand one another. A shared legacy IRQ is one hardware routing unit, so its other users share the resulting CPU restriction.
- Placement filters node/package/cache/CPU candidates; affinity activation also intersects with the pool, online CPUs and global CPU bans. Higher-level affinity masks cannot leak into excluded CPUs.
- Invalid rules, reversed/out-of-range CPU ranges, empty lists and malformed separators are rejected before daemon startup. The CPU limit is the existing irqbalance bitmap capacity (4096 CPUs), not a 32/64-bit mask limit. Offline CPU IDs are valid configuration and become usable when online.
- An empty effective pool is logged once while pending. The daemon does not write an empty or out-of-pool affinity and retries when placement becomes possible. Existing/kernel-selected affinity is left unchanged while no legal target exists; this cannot provide CPU isolation when the requested pool is unavailable.
- Explicitly banned and kernel-unmanaged IRQs remain unmanaged. Driver/kernel restrictions may reject affinity changes through irqbalance's existing error handling.
- IRQ database discovery/rebuild applies current rules to the discovered sysfs device. CPU hotplug uses the existing rebuild path. Send SIGHUP after interface renaming, or if the netdev appeared after its IRQ was first discovered. Changing CLI/UCI rule values requires a service restart.
- This applies to PCI-backed interfaces discoverable by irqbalance's existing PCI IRQ database. It does not claim per-port IRQ separation for virtual interfaces or USB NICs sharing a USB-controller interrupt.

## Source and checks

Package: `feeds/packages/utils/irqbalance`. Source patch: `patches/030-netdev-cpu-pools.patch`. The recipe release is incremented, and the init script passes each UCI entry as a separate quoted argument.

```sh
make package/feeds/packages/irqbalance/compile -j4 V=s
python3 scripts/tests/test-irqbalance-netdev-cpus.py
python3 scripts/tests/test-irqbalance-netdev-cpus.py --native
```

The native check requires user/mount namespaces, a PCI NIC, host GCC and the prepared OpenWrt hostpkg GLib headers. It executes the built daemon in a private mount namespace with `/proc/irq` read-only, captures affinity writes using a test-only interposer, and checks that only matching IRQs acquire the CPU-pool restriction. It does not change host IRQ affinities or install/restart any system service.

The source patch is regenerated with the package's quilt refresh target. See [validation](irqbalance-netdev-cpus-validation.md) for exact results and artifact identity. Package publication, router installation and physical IRQ/performance validation are separate steps; the previous RPS benchmark did not test this IRQ feature.
