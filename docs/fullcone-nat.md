# Full cone NAT (NAT1)

firewall4 can masquerade IPv4 UDP with endpoint-independent mapping and
filtering (RFC 4787, "full cone" or NAT1). Once a LAN host has sent from a
UDP port, any remote host can reach that host through the router's external
port, which games, VoIP and peer-to-peer applications use for direct
connections. The feature is backported from coolsnowwolf/lede and ported to
Linux 7.3. It is **off by default**.

## Enable

In LuCI, open *Network → Firewall* (`luci/admin/network/firewall`), tick
**Enable full cone NAT** under *General Settings* and click *Save & Apply*.
The checkbox writes `fullcone='2'` when ticked and removes the option (the
same as `0`) when cleared; it is shown only on firewall4 systems. Any other
value, such as a leftover `fullcone='1'`, shows as unticked and is removed the
next time that page is saved.

From the shell:

```sh
uci set firewall.@defaults[0].fullcone='2'
uci commit firewall
fw4 reload
```

`fw4 reload` logs `IPv4 brcm fullcone enabled for zone 'wan'` for each zone
with `masq`, and the ruleset shows `meta nfproto ipv4 masquerade fullcone`
in `srcnat_wan`. Disable with `fullcone='0'` (or delete the option) and
reload. Changing the mode does not affect connections that are already
tracked.

## Installing on a router

The kernel side needs a new kernel generation and a reboot; the rest is
userspace.

1. Publish a build with `build-and-publish.py`, which reserves the kernel
   generation.
2. `apk upgrade` on the router. `CONFIG_NF_NAT_MASQUERADE_FULLCONE=y` in
   `target/linux/generic/config-7.3` changes the kernel ABI hash
   (`2a97e7c5…` → `2f47df10…` for the current x86/64 configuration), so this
   is a real ABI change: APK installs the new kernel and the complete kmod set
   as a new generation and arms a trial boot, instead of printing
   `Keeping installed kernel generation: ABI unchanged.`
3. Reboot into the trial and confirm it with `kernelctl check`
   (see [kernel upgrades](kernel-upgrade.md)).
4. Enable full cone NAT as below.

The userspace packages are safe on the old kernel: fullcone is off by default,
and an old kernel ignores the `fullcone` attribute and masquerades normally.

## Options (`config defaults`)

| Option | Values | Meaning |
| --- | --- | --- |
| `fullcone` | `0` | Ordinary masquerading (default). |
| | `2` | Broadcom-style full cone: `masquerade fullcone` on IPv4; UDP gets full cone, TCP and other protocols are masqueraded as usual. |
| | `1` | Out-of-tree `nft_fullcone` expression. **Not available in this tree**; fw4 probes it, logs `nft_try_fullcone failed, disable fullcone globally` and falls back to ordinary masquerading. |
| `fullcone6` | `0`/`1` | IPv6 full cone through `nft_fullcone`. Not available; probed and disabled the same way. |

## How mode 2 works

- The kernel (`target/linux/generic/hack-7.3/982-…`, `983-…`) adds a
  `BCM-NAT` conntrack helper that is registered while a masquerade user
  (nft or iptables) is loaded.
- The first UDP flow of an internal `address:port` picks an external port,
  keeping the internal port when it is free and otherwise the next free port
  of the same parity, and installs a permanent expectation for
  `external-address:port` from any remote host. Later flows from the same
  internal endpoint reuse the port.
- An unsolicited packet from any host to that port matches the expectation
  and is forwarded to the internal endpoint; no port forward is needed. The
  mapping lasts as long as the first flow's conntrack (UDP timeouts, refreshed
  by traffic).
- If no port is free, the helper is unavailable or the expectation table is
  full, the flow is masqueraded normally rather than dropped.

## Operational notes

- **Exposure.** Any internet host can send UDP to an active mapping. This is
  the point of NAT1, but it is weaker filtering than the default
  port-restricted behaviour. The `wan` input/forward policies still apply to
  everything else.
- **Expectation limit.** Each active internal UDP endpoint uses one
  conntrack expectation. Check `sysctl net.netfilter.nf_conntrack_expect_max`
  (the kernel default is four times the expectation hash size, often only a
  few thousand); when it is reached new endpoints silently fall back to
  ordinary masquerading. Raise it if needed, for example
  `echo 'net.netfilter.nf_conntrack_expect_max=16384' > /etc/sysctl.d/90-fullcone.conf`.
- **Flow offloading.** Software and hardware flow offloading skip conntracks
  with a helper, so the flow that creates a mapping stays on the slow path.
  Later flows that reuse the mapping can still be offloaded.
- **Inspection.** `cat /proc/net/nf_conntrack_expect` (as root) lists
  mappings as `PERMANENT BCM-NAT` entries with the external port in `dport`.
  Linux 7.3 does not print `helper=` in `/proc/net/nf_conntrack`.
- **Proxies.** Traffic that passwall (or another tproxy) intercepts never
  reaches the router's masquerade, so it gets the proxy's NAT behaviour, not
  full cone. Only directly routed UDP uses the router's mapping.
- **Upstream NAT.** If the WAN address is private (carrier-grade NAT), the
  NAT type seen from the internet also depends on the ISP's NAT. Check with a
  STUN NAT-type test from a LAN host, using a server that is routed directly.
- **Older kernels.** Userspace runs on a kernel without patch 983, but the
  kernel ignores the `fullcone` attribute there and masquerades normally.
  Install the matching kernel generation before relying on NAT1.

## Not carried from LEDE

- `hack-6.18/984-netfilter-reserve-unconfirmed-nat-tuples.patch` adds a global
  lock and allocation to every NAT setup on the router; mainline resolves the
  race it targets when the conntrack is confirmed.
- The `fullconenat-nft` (`kmod-nft-fullcone`) module and the
  `952-…conntrack-events…` hack it needs for chained conntrack notifiers;
  without that hack it would take the single conntrack event notifier slot.
- LEDE's firewall4 default of `fullcone 1` and its `flow_offloading`
  defaults.

## Sources

| Component | Change |
| --- | --- |
| Kernel | `hack-7.3/982-netfilter-add-bcm-fullcone-masquerade.patch` (ported to the refcounted 7.3 helper API; LEDE 982 + 985; adds `CONFIG_NF_NAT_MASQUERADE_FULLCONE`), `983-netfilter-nft_masq-add-fullcone-attribute.patch` (LEDE 983); recorded in `configs/mainline-kernel-patches.json` |
| Kernel config | `CONFIG_NF_NAT_MASQUERADE_FULLCONE=y` in `target/linux/generic/config-7.3`; without it the code is not built and `masquerade fullcone` behaves like `masquerade` |
| libnftnl | `001`, `002` (`1.3.2-r4`); 001 adapted to the 1.3.2 `set` callback |
| nftables | `100`, `103`, `104` (`1.1.7-r4`); 100 and 103 rebased onto 1.1.7 |
| firewall4 | `001`, `002`, `007` from LEDE (001/002 rebased, shipped disabled); `008` probes `fullcone6` so enabling it cannot break the ruleset load (`r2`) |
| LuCI | `feeds/luci` commit `51551b1c9c` (`luci-app-firewall` `view/firewall/zones.js`: *Enable full cone NAT* checkbox, with zh_Hans/zh_Hant strings), mirrored as `patches/feeds/0029-luci-firewall-fullcone.patch` with baseline `configs/firewall-fullcone-feeds.json`; test `scripts/tests/test-luci-firewall-fullcone.js` |

See the [validation record](fullcone-nat-validation.md).
