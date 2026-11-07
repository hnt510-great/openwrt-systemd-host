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

# r2: LLM-ready output and local model evaluation — 2026-11-06

Design and model research: `docs/router-audit-llm-plan.md`. Guide: `docs/router-audit.md`.
Evidence workspace (outside the repository): `/srv/openwrt-validation/router-audit-llm-test-20261106/`
(`runs/` holds every report, eval result, server log and power sample).

## Scope

router-audit 1.0.0-r2 was built and tested on Debian only. It was **not published and not installed
on the router**; the router still runs r1 (schema 1.0), whose data the r2 analyzer reads through
`normalize.upgrade()`. daed and dnsmasq were not changed. The model runtime ran temporarily from the
evidence workspace and was stopped; no package, unit, autostart, PATH change or MCP registration was
added on Debian. A GRUB drop-in enabling GPU overdrive was added for a planned clock test and removed
again before any reboot (the test was dropped); `/etc/default/grub` was never edited.

## Source and build checks

| Check | Result |
| --- | --- |
| `python3 scripts/tests/test-router-audit.py` | 28 tests passed (collector, normalize/upgrade, fixtures, renderers, derived cache, explain against a fake endpoint incl. retry/fallback/time budget/pinned fields, MCP over stdio) |
| `python3 scripts/tests/test-custom-package-updates.py` | 47 tests passed |
| `make package/custom/router-audit/compile V=s` | passed; `router-audit-1.0.0-r2.apk` SHA-256 `5759dcc44bbe9c9d253259b6208a0ce30d2ed2c73eaf3a39649615bfc9597a4c` |
| Package payload | collector, `router-audit-normalize.py`, wrappers, unit, sudoers, `analyze.py`, `explain.py`, `mcp_server.py`, `normalize.py`, `pull.py`, `schema.json`, six prompt files |
| Installed layout | extracted payload: collector `capabilities` returns schema 1.1 with `Z` timestamps; `analyze.py` and `mcp_server.py` load `normalize.py` from their own directory |
| `git diff --check` | passed |

## Real router data (read-only)

The restricted `router-audit` SSH entry was used with `pull.py` into the workspace. The first pull
returned only 15 minutes, which exposed a puller gap (first run inherited the export default); after
the fix the first run backfilled the whole router buffer: 1,039 records, 107 minute samples. The r2
analyzer read the r1 data through the 1.0 upgrade path.

The first analysis produced six warnings that inspection showed were false positives, all fixed and
covered by fixtures/tests: three one-shot procd instances (`urandom_seed`, `acme`, `sysstat`:
`inactive`, exit status 0), two DNS error ratios driven by PTR (`ip6.arpa`) NXDOMAIN, and `eth1`
receive drops (46k of 12M frames, typical unhandled-protocol counting) reported as a warning.
Baselines also accepted 40 minutes of history; a verdict now needs 24 hours. After the fixes the
window yields one `info` finding (eth1 receive drops) and all baselines report `no baseline yet`.

## Model evaluation

Runtime: llama.cpp b12143 (commit `2bc46baa9`) prebuilt Vulkan x64, archive SHA-256
`dd983d8eaa85e1e71fba4458441b6a507f86bb50db6b5675d1e6aa788ecccbfc`, on the Radeon RX 6600 XT
(RADV NAVI23, 8 GB; desktop baseline 778 MiB). Server: `-np 1 -ngl 99 -fa on`, q8_0 KV cache,
`--jinja`, 127.0.0.1 only. All GGUF files matched their Hugging Face SHA-256:

| Model | Source | SHA-256 | Context |
| --- | --- | --- | --- |
| Qwen3.5-4B Q6_K | `unsloth/Qwen3.5-4B-GGUF` | `fdedd781c9ce676ab66b018ca247ff78e8a33c98098a822c1e2d5075e7718f66` | 32k |
| Granite 4.2 8B Q4_K_M | `ibm-granite/granite-4.2-8b-GGUF` | `16a9369d0805f80b7377d25d87f937a90c05dc04ad79173a52001e42c9aab311` | 16k |
| Qwen3.5-9B Q4_K_M | `unsloth/Qwen3.5-9B-GGUF` | `03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8` | 32k |

Fixtures: `scripts/tests/router-audit-fixtures.py` (7 days baseline, first 3 days schema 1.0, one test
hour): quiet, WAN flap, conntrack 90 %, NXDOMAIN storm, random-looking names, failed unit, memory
pressure with OOM. Scores from `scripts/tests/router-audit-llm-eval.py`.

### Final comparison (identical code, default settings: budget 4000, `llm` text, thinking off, pipeline)

| Check | Qwen3.5-4B Q6_K | Granite 4.2 8B Q4_K_M | Qwen3.5-9B Q4_K_M |
| --- | --- | --- | --- |
| Valid JSON | 100% | 100% | 100% |
| Category / severity within one level | 100% / 100% | 100% / 100% | 100% / 100% |
| Expected issue named in summary (6 faults) | 6/6 | 6/6 | 6/6 |
| Overall verdict right (incl. quiet = `ok`, no issues) | 7/7 | 7/7 | 7/7 |
| Invented finding IDs | 0 | 0 | 0 |
| Tool choice (10 questions) | 9/10 | 8/10 | 8/10 |
| Real data: overall | `ok` | `attention` (only an `info` finding; prompt says `ok`) | `ok` |
| Time for 7 fixtures | 64 s | 93 s | 90 s |
| Generation / prompt processing | 56 / 580–960 tok/s | 42 / 490–620 tok/s | 41 / 550–650 tok/s |
| VRAM incl. desktop | 4.8 GB | 7.1 GB | 6.4 GB |

**Default: Qwen3.5-4B Q6_K, thinking off.** Equal accuracy, fastest, most VRAM headroom, best tool choice.

### Setting sweep (one factor at a time, before the last two schema fixes)

| Setting | 4B | Granite 8B | 9B |
| --- | --- | --- | --- |
| budget 3k / 8k / 16k | same as 4k (8k/16k fixed one relabel) | all 100% | same as 4k |
| `llm-json` input | one overall verdict wrong | 100% | more category relabels |
| thinking on | 6 fixtures in 1,492 s, 2 answers never valid JSON (ran out of tokens) | 6 fixtures in 803 s, all valid | not run |
| agent mode (MCP tools) | same verdicts, 85 s, 3–8× input tokens | same verdicts, 146 s | same verdicts, 145 s |

Thinking runs were stopped after six fixtures and removed from the standard sweep; `explain.py`
has a per-request timeout, a whole-run time budget and a reasoning-token cap. Two defects found by
the eval were fixed in code: summaries padded `top_issues` with a filler `"none"` ID, and models
relabelled the copied `category` field (`conntrack` → `network`). The summary schema is now built
per window (IDs limited to real findings, list no longer than the findings) and each finding's schema
pins `id` and `category`. Tool descriptions were reworded after the first tool run (4B: 7/10 → 9/10).

### GPU power (Qwen3.5-4B, fixed 4-report workload)

| State | Time | Energy | Avg / peak power | Peak junction | Generation |
| --- | --- | --- | --- | --- | --- |
| default (auto, BOOTUP_DEFAULT, 130 W) | 44.4 s | 5,224 J | 118 / 130 W | 102 °C | 56.1 tok/s |
| POWER_SAVING profile | 44.4 s | 5,257 J | 119 / 126 W | 104 °C | 56.1 tok/s |
| COMPUTE profile | 44.0 s | 5,272 J | 120 / 130 W | 107 °C | 56.2 tok/s |
| 122 W cap (driver minimum) | 44.4 s | 5,126 J | 115 / 123 W | 104 °C | 56.1 tok/s |
| manual core clock level (2655 / 500 MHz) | 44.4 s | ~5,280 J | 119 / 130 W | 105 °C | 56.2 tok/s (level did not hold) |
| memory clock 675 MHz | 60.6 s | 5,941 J | 98 / 130 W | 102 °C | 39.9 tok/s |

Answers were byte-identical in every state. The card is power-limited during generation; without
overdrive no state saves more than 2%, and a lower memory clock costs more energy than it saves.
GPU idle was 4.9 W with and without the model loaded. A finer core-clock cap needs the overdrive boot
option; it was prepared, judged not worth a permanent host change for a few Wh per day, and removed
unused. The GPU was returned to `auto` / 130 W.

## Deployment after validation

At the user's request r2 was then published (snapshot `20261106T051640.011628Z`, preflight passed,
only `router-audit-1.0.0-r2.apk` changed) and installed on the router with `apk add -u router-audit`
(simulation showed only that upgrade), followed by `systemctl restart router-audit-collect.service`.
The first r2 batch was schema 1.1 for every module, all 65 firewall rules carried their comment, no
DNS client kept a port, an incremental restricted-SSH pull succeeded and LAN DNS answered over IPv4
and IPv6. r3 (conntrack loss rated per hour; analyzer only) was published as snapshot
`20261106T052212.303924Z` and not installed on the router. A user-level minute puller was then set
up on Debian; see `router-audit-debian.md`.

## Known limits

No reboot was performed for r2. Baselines need 24 hours of
pulled history before verdicts appear. The fixtures are synthetic and small; they test that faults are
named and nothing is invented, not diagnosis quality on unusual real incidents. Model throughput was
measured on one GPU with one llama.cpp build. Periodic beaconing detection is not implemented.

# r4: connection events and conntrack snapshot — 2026-11-06

| Check | Result |
| --- | --- |
| `scripts/tests/test-router-audit-connections.py` | 8 tests passed (conntrack parsing incl. expanded IPv6 and accounting fields, directions, DNAT, limits, event validation, flow grouping, root-only receiver) |
| `test-router-audit.py`, `test-custom-package-updates.py` | 29 and 47 tests passed |
| daed r7 build | patch `009-connection-audit-events.patch` refreshed with quilt (older patches' formatting-only refresh changes restored); binary contains the `conn.sock` path; gofmt clean |
| Pre-install dry run on the router | temporary copy of the r4 collector: 224 conntrack lines → 50 groups, accounting on, not truncated |
| Publication | dry run and preflight passed; snapshot `20261106T064602.832657Z` with daed, daed-geoip, daed-geosite 2.1.1-r7 and router-audit 1.0.0-r4; no same-version rebuilds |
| Router install | `apk add -u --simulate` showed exactly those four upgrades; installed 14:46; daed and the collector restarted (new PIDs, NRestarts 0); daed environment has `ROUTER_AUDIT_DNS=1` and `ROUTER_AUDIT_CONN=1`; `/run/router-audit/conn.sock` present; the stale `/usr/libexec/__pycache__` is gone |
| First live minute | `conn_flows`: 80 events, 60 flows (TCP/UDP via `proxy`, TCP `direct`), 49 with a sniffed domain, 21 with a MAC, receiver and producer drops 0. `connections`: 82 groups (51 lan_out, 19 router_out, 6 lan_local, 6 inbound), not truncated |
| Traffic after the daed restart | LAN DNS answered; HTTPS through the router returned 200 in 0.55 s |

Scope: the analyzer does not read the new modules yet. No reboot, UCI or firewall change; the
APK uci-history hook reported no configuration change. Proxied connections were interrupted once
while daed restarted.


## Audit SSH account Podman masks — 2026-11-06

Repeated failures belonged to UID 999 (`router-audit`), not Hermes. Each minute
SSH pull created a fresh user manager and started globally enabled Podman units;
Podman failed with `stat /home/router-audit/.config: no such file or directory`.
Root-owned per-account masks for `podman-restart.service`,
`podman-auto-update.timer`, `podman-auto-update.service`, `podman.socket`, and
`podman.service` were installed in `/home/router-audit/.config/systemd/user` on
the physical router at 19:43:47 +08. The 19:44 login read the next sample cursor
successfully without starting Podman or logging its previous failure. Existing
Example user containers (ubuntu, ariang, searxng) remained running. No UCI change,
container restart or reboot was needed. Enrollment instructions now preserve
this account-specific configuration; the package release is reserved as r5
because its installed README changes. No feed publication or APK upgrade is
part of this fix.

Validation: `git diff --check` passed;
`make package/custom/router-audit/compile V=s` completed successfully and built
`router-audit 1.0.0-r5`. The 19:45 audit SSH pull also succeeded with an advanced
sample cursor and no Podman startup/failure. Build log:
`/tmp/router-audit-podman-mask-build.log` on Debian. The masks are an enrollment
configuration step, not an automatically applied package post-install action.
