# Mainline 7.3 Kernel Patch Review

The complete per-patch JSON ledger (`configs/mainline-kernel-patches.json`) has been retired because it had no build, test, or script consumers and drifted from live `PKG_RELEASE` bumps.

The authoritative source of truth for the Linux 7.3 patch stack is:
- Git history on `target/linux/generic/*-7.3/` and `target/linux/x86/patches-7.3/`
- Zero-fuzz patch verification performed by `scripts/update-mainline-kernel.py --update`

Non-OpenWrt-upstream kernel/module patches carried in tree:
- `target/linux/generic/hack-7.3/252-netfilter-keep-nfnetlink-modular.patch`
- `target/linux/generic/hack-7.3/982-netfilter-add-bcm-fullcone-masquerade.patch`
- `target/linux/generic/hack-7.3/983-netfilter-nft_masq-add-fullcone-attribute.patch`
- `target/linux/x86/patches-7.3/992-drm-i915-load-huc-on-gen9-11.patch`
- `package/kernel/mac80211/patches/build/021-kernel-7.3-hex-helpers.patch`

## Known Optional-Config Issue

- **MAP-E `ip6_tunnel.c` compilation error (`CONFIG_IPV6_TUNNEL=y`, unset in current configs)**: `target/linux/generic/pending-7.3/666-Add-support-for-MAP-E-FMRs-mesh-mode.patch` changes `HASH()` in `net/ipv6/ip6_tunnel.c` to take one argument (line 77), while two wildcard lookup calls at lines 155 and 168 still pass two arguments (`HASH(&any, local)` and `HASH(remote, &any)`). Zero-fuzz patch application does not catch this because `CONFIG_IPV6_TUNNEL` is unset.
