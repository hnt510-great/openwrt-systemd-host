# dnsmasq nftset fast path validation

Validated on 2026-11-01 on the build host. The packages were built and tested
in a QEMU guest, then published with kernel generation 43 (see the
[full cone record](fullcone-nat-validation.md)); the router preflight
simulated `dnsmasq-full` r9 → r10. **Nothing was installed on the router** and
no image was built.

## Artifacts

| Package | SHA256 |
| --- | --- |
| `dnsmasq-full-2.93-r10.apk` | `1f882a2a5bf70ef496a7260e8163ee644ef593e194842921c8ab9b6b47ab65d2` |
| `nftables-json-1.1.7-r4.apk` | `4db422c4aef663437acdb2f57099925547562876ed53741b303a5284161c6e14` |
| `libnftnl11-1.3.2-r4.apk` | `08ae6627d8d17c457b78e8243fea026764036ccdf8011d50ea34d488c4781467` |

## Source and build checks

| Check | Result |
| --- | --- |
| `230-nftset-netlink-address-sets.patch` on dnsmasq 2.93 after the fork's patches | Applies with fuzz 0 |
| nftables `105-cache-target-set-elements.patch` on 1.1.7 after 100/103/104 | Applies with fuzz 0 |
| Code review of the netlink path | Key type and length checked, generation-guarded batch, fallback on any error; a miss (`ENOENT`) also closes and later reopens the socket |
| `make package/network/services/dnsmasq/{clean,compile}` | Pass; `dnsmasq` `NEEDED` now includes `libnftnl.so.11` and `libmnl.so.0`, matching the added dependencies |
| Release identity | dnsmasq `r10` (published: `r9`); nftables `r4` (see the full cone record) |

## Behaviour (QEMU/KVM guest)

The test dnsmasq forwarded to a second dnsmasq acting as upstream, with
`--cache-size=0` and `nftset=` rules pointing at each kind of set.

| Check | Result |
| --- | --- |
| Plain `ipv4_addr` set (`inet`) | Answered; element present |
| Interval set, new address (libnftables fallback) | Answered; element present |
| Interval set, address inside an existing `/24` | Answered; `/24` left intact |
| Set with `flags timeout; timeout 1h` | Answered; element present with the default expiry |
| Plain set in an `ip` table | Answered; element present |
| Duplicate addition | Answered; one element |
| Set deleted and recreated as an interval set under the same name | Answered; element present (no stale metadata) |

## Latency

The same guest loaded a 20,000-prefix interval set (`inet big chn`) and ran
100 sequential queries per row against dnsmasq. `none` names have no
`nftset=` rule and give the per-query baseline, which is dominated by
spawning the query tool. "Previous" are the published `dnsmasq-full 2.93-r9`,
`nftables-json 1.1.7-r3` and `libnftnl11 1.3.2-r3` from the build root. The
kernel is the KASAN/lockdep debug build, so absolute numbers are inflated.

| dnsmasq + libnftables | none | plain set | interval set |
| --- | --- | --- | --- |
| previous + previous | 349 ms | 517 ms | 398 ms |
| new + previous | 341 ms | 367 ms | 372 ms |
| new + new | 343 ms | 372 ms | 377 ms |

The same run on the production kernel configuration (no KASAN), from
`vm/vm-run-production-config.log`:

| dnsmasq + libnftables | none | plain set | interval set |
| --- | --- | --- | --- |
| previous + previous | 52 ms | 134 ms | 56 ms |
| new + previous | 53 ms | 53 ms | 52 ms |
| new + new | 50 ms | 53 ms | 53 ms |

On the debug kernel, nftset overhead per query for the plain set fell from
about 1.7 ms to about 0.3 ms, and for the interval set (auto-merged, address
already covered) from about 0.5 ms to about 0.3 ms. On the production kernel
the plain-set overhead fell from about 0.8 ms to about 0.03 ms. 105 had no
measurable effect here because these queries take the netlink path; it
applies to fallback additions (new interval boundaries, timeout intervals).

## Router

After the upgrade the router runs `dnsmasq-full-2.93-r10` with `libnftnl`
and `libmnl` loaded. Its passwall uses `dns_shunt chinadns-ng`, which fills
the `psw_*` sets itself, and no dnsmasq configuration contains `nftset=`, so
the fast path is installed but not used there.

## Scope

Not checked: passwall's own sets and ruleset on a router, IPv6 sets, real
upstream DNS, a firewall reload racing an update, and long-running use. The
benchmark is synthetic and single-client.

**Evidence:** `/srv/openwrt-validation/fullcone-nftset-validation-20261101/`
(`vm/vm-run.log` and `vm/vm-run-production-config.log`, sections F and G;
`build-logs/dnsmasq.log`).
