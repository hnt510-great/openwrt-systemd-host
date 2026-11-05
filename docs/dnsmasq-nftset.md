# dnsmasq nftset fast path

`dnsmasq-full` with `nftset` support adds every resolved address that matches
an `nftset=` rule to an nftables set before it answers the query. Passwall's
nftables transparent proxy relies on this for its domain-based sets. Upstream
dnsmasq does each addition through libnftables, which builds a full ruleset
cache, including every element of every interval set, for each address. With
large routing sets loaded, DNS replies stall behind that work.

Two patches from coolsnowwolf/lede remove most of that cost. No configuration
is needed.

## Behaviour

- **dnsmasq** (`package/network/services/dnsmasq/patches/240-nftset-netlink-address-sets.patch`,
  `2.93-r10`): plain IPv4/IPv6 address sets are updated directly over
  netlink. dnsmasq reads the set's current metadata (never a cached copy, so a
  firewall reload that recreates a set is seen immediately) and commits the
  element in a batch guarded by the ruleset generation ID, then waits for the
  kernel's acknowledgement before answering. For auto-merged interval sets
  without timeouts it asks the kernel whether the address is already covered
  and skips the update if so.
- Everything else still goes through libnftables exactly as before: new
  interval boundaries, sets with timeouts on intervals, maps, concatenated or
  non-address key types, sets with expressions, deletions, and any netlink
  error, including a ruleset change between the metadata read and the commit.
- **nftables** (`105-cache-target-set-elements.patch`, `1.1.7-r4`): for a single
  `add element` command, libnftables now dumps only the elements of the
  target set instead of every interval set. Batches, echo mode and all other
  commands still load the full cache.

Duplicate additions keep the semantics of `add element` (no error), and a
set's default timeout still applies to netlink-added elements.

## Dependencies

`dnsmasq-full` now links `libnftnl` and `libmnl` directly when
`CONFIG_PACKAGE_dnsmasq_full_nftset` is set; both are already pulled in by
`nftables-json`. The other dnsmasq variants are unchanged.

## Recovery

Both changes are transparent fallbacks around the existing code. To rule them
out, install the previous `dnsmasq-full` and `nftables-json` packages from the
feed, or remove the two patches and rebuild. Errors from the libnftables path
are still logged as `nftset <family table set> <nft error>`.

See the [validation record](dnsmasq-nftset-validation.md).
