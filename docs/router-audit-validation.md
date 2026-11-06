# Router audit validation — 2026-11-06

## Delivered state

Build host: Debian checkout `/srv/openwrt`. Physical target: N5105 OpenWrt Systemd Host, kernel `7.3.1-51-openwrt`, systemd 262.

Final installed packages, built by this checkout and published through the existing LAN feed workflow:

| Package | Version |
| --- | --- |
| router-audit | 1.0.0-r1 |
| daed | 2.1.1-r6 |
| dnsmasq-full | 2.93-r14 |

Production uses APK-owned `/usr/bin/daed`, `/usr/sbin/dnsmasq`, `/usr/libexec/router-audit*` and `/usr/lib/systemd/system/router-audit-collect.service`. Temporary `/usr/local/libexec/router-audit-bin`, old local wrappers and the router-local compiler/source cache were removed. There is no maintained second production binary tree. Existing UCI values, DNS routing and credentials were preserved; package default `.apk-new` files were not applied.

## Source and build checks

- `python3 scripts/tests/test-router-audit.py`: 4 tests passed (duration bounds, module failure isolation, internal-query separation, unavailable source).
- `python3 scripts/tests/test-custom-package-updates.py`: 47 tests passed.
- `make package/custom/router-audit/compile V=s`: passed.
- `make -j4 package/custom/daed/compile package/network/services/dnsmasq/compile V=s`: passed.
- `make .../prepare QUILT=1` and `make .../refresh`: both DNS patches applied/refreshed. Formatting-only changes regenerated in older patches were restored to avoid unrelated edits.
- `git diff --check`: passed.
- Kernel `checkpatch.pl` was run against the dnsmasq patch. It reports GNU-style indentation/braces and patch-header metadata; this is not a clean kernel-style result. The helper follows the neighboring userspace GNU layout. Compilation and physical DNS checks passed.

No full firmware build, high-QPS stress test, reboot test or production fault injection was performed. These are not prerequisites for this first deployment.

## Official publication and installation

Ran the repository's existing method, with the default `configs/lan-apk-feeds.json`:

```
./scripts/publish-changed-feeds.sh --dry-run --no-progress
./scripts/publish-changed-feeds.sh --no-progress
```

Userspace publication succeeded at:

```
/srv/openwrt-feeds/public/snapshots/20261106T021933.287313Z
```

No same-version rebuild violations. Signature, immutable-version and router upgrade preflight passed. Kernel channel remained unchanged. The publisher included daed/geoip/geosite r6, dnsmasq r14, router-audit r1 and a previously built pending edid-decode r4. Only the three audit-related packages above were reinstalled on the physical router; no kernel/edid/general upgrade was requested.

On the router:

```
sudo apk update
apk fetch --output /tmp/router-audit-published daed dnsmasq-full router-audit
sudo apk fix --reinstall daed dnsmasq-full router-audit
```

The downloaded official-feed payloads matched the previously built package identities. For this same-version reinstall, the fetched payloads populated APK's normal identity-named cache before `apk fix` authenticated and installed them. The customized managed payload preflight rejects `--no-cache` reinstall and does not prefetch a missing same-version payload; that attempted command failed before writes. No signature, payload-preflight or immutability guard was bypassed, and APK itself was not modified.

## Installed/build synchronization

SHA-256 equality was checked against the final stripped `ipkg-x86_64` payloads (not the unstripped `.pkgdir` staging binaries):

| Installed executable | SHA-256 |
| --- | --- |
| `/usr/bin/daed` | `b086a976967f12a3d41bee4ca70bb3a12aa705fc7f576c055a2869d8e9cc83d8` |
| `/usr/sbin/dnsmasq` | `2555790617e3fa7e795d6bcb1da97420d5521e9f538a30f0d1ae453323c7f491` |

Also matched byte-for-byte against tracked source: audit collector, read wrapper, SSH wrapper, collector unit, daed init script and dnsmasq init script. APK reports ownership of both DNS executables and the collector.

## Physical behavior

- Collector, daed and dnsmasq active with successful exit status; collector NRestarts=0 at final check. Observed collector memory approximately 23–24 MiB, not a long-term peak claim.
- Post-feed-install LAN DNS: 12 checks passed — IPv4/IPv6 × UDP/TCP × A/AAAA/negative name. Positive RCODE=0, negative RCODE=3.
- Both daed and dnsmasq events observed in sealed spool batches, including QTYPE/RCODE and source timestamps. Loopback dnsmasq records are separately marked as internal by minute aggregation.
- Snapshot modules system/network/services/firewall/identity/virtualization returned usable data. DNS/history/incidents deliberately report partial coverage.
- Restricted SSH export from Debian passed. An arbitrary `id` command was rejected.
- Samples cursor paging moved to the next record correctly.
- Debian puller final test: 164 stored batches after first pull and still 164 after immediate second pull. SQLite cursor/record insertion and batch deduplication worked.
- Analyzer generated valid JSON from that database. Temporary validation databases stayed under Debian `/tmp`; no permanent analysis timer/database was provisioned.

## Known limits

This is an initial working interface, not comprehensive monitoring. Learned DNS baselines, periodic C2 detection, direct per-upstream DNS latency, full per-client active connections and Podman runtime health are not implemented. dnsmasq events describe sent responses, not all received queries. Client encrypted DNS and other uninstrumented paths remain invisible. Journal scan and DNS queue limits can lose coverage; output exposes partial/truncation/drop information. No automatic external-LLM anonymization is claimed. See `router-audit.md` for retention, privilege boundaries and rollback.

Personal SSH public keys, credentials, databases, generated APKs and local backups are intentionally excluded from Git. Pre-existing unrelated working-tree changes are left untouched. No Git push was performed.
