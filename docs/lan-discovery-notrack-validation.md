# LAN discovery notrack validation

Validated on 2026-11-02 on the build host only. The package was built but
**not published or installed**; no image was built or booted and no physical
device was touched.

## Artifacts

| Artifact | SHA256 |
| --- | --- |
| `bin/systemd/packages/x86_64/base/firewall4-2026.10.29~e6f600c4-r3.apk` | `c7b37d88980a875ede6665469d4f2fbdaea64ea6bdafbd7b4b035275dd42b784` |

## Checks

| Check | Result |
| --- | --- |
| `make package/network/config/firewall4/{clean,compile}` | Pass; all six patches apply, payload has `95-upnp-ssdp-notrack` and `96-wsd-notrack` |
| Release identity | `r3`; published feeds hold `r1` and `r2` only |
| Upstream fw4 test suite (`run_tests.sh`, host ucode) | 40/40 pass with the patch stack |
| fw4 render of a `lan`/`wan` config with the three rules | `raw_prerouting` jumps `notrack_lan` on `br-lan`; chain holds `ip daddr 239.255.255.250 udp dport 1900`, `… 3702` and `ip6 daddr ff02::c udp dport 3702` with `notrack` |
| Migrations on the default fw4 config (target `uci` via target loader, bash for ash `export -n`) | Three sections added with the expected options |
| Second run | No change (rule count stays at default + 3) |
| Existing `upnp_ssdp_notrack` with `enabled='0'` | Preserved unchanged |
| Config without a `lan` zone | No sections added |

Not checked: loading the ruleset into a kernel, discovery from real LAN
clients, BusyBox ash itself, and an APK upgrade on the router.

**Evidence:** command output in the session on 2026-11-02; the fw4 render and
UCI fixtures were kept in a temporary scratch directory only.
