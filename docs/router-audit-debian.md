# Router audit: Debian analysis host state and handover

Status as of 2026-11-06 13:30 +08. This records what exists on the Debian analysis host (the build
host that runs this checkout) for router-audit, what was deliberately not done, and what the next
step — building the actual local LLM analyzer for the router's data — can rely on.

Read in this order: `router-audit.md` (guide: collector, data contract, analyzer, explain/MCP,
model guidance), `router-audit-llm-plan.md` (design rationale and the 2026 model research),
`router-audit-validation.md` (r1 deployment and the r2 measurements), then this file.

## Versions and where they run

| Component | Version | Where |
| --- | --- | --- |
| Collector (`router-audit-collect.service`, schema 1.1 + `connections`/`conn_flows`) | 1.0.0-r4 installed 2026-11-06 14:46 | physical router `192.0.2.1` |
| daed with DNS and connection audit hooks | 2.1.1-r7 installed (geoip/geosite r7) | physical router; snapshot `20261106T064602.832657Z` |
| Debian scripts | r3, commit `b7cb955d13` | `/srv/openwrt-validation/router-audit/` (copies, see below) |

Router changes, publication and installation need the user's explicit
authorization each time (see `CLAUDE.md`).

## New data for the analyzer (r4, daed r7)

The collector adds two modules that `analyze.py` does not read yet (left to the analyzer work):
`conn_flows` (daed: device → real destination IP/port, sniffed domain, outbound, failures, per
minute) and `connections` (conntrack snapshot: direct and NAT-ed flows by direction, client,
destination and port). The data contract is in `router-audit.md` ("Connections"). Suggested use:
join `conn_flows`/`connections` with the same client's `dns_queries` answers to name IP-only
destinations, resolve clients with the existing identity mapping, and treat the result as private
per-device browsing data. Fixture coverage exists only for the collector side
(`scripts/tests/test-router-audit-connections.py`); `router-audit-fixtures.py` does not generate
these modules yet. The Debian script copies in `/srv/openwrt-validation/router-audit/` are unaffected:
`pull.py` stores the new records like any other module.

## Permanent Debian state (the only permanent change)

The user approved a minute puller so that baselines can accumulate. Everything is user-level; no
root, package, system unit or boot change exists for router-audit.

| Item | Path / value |
| --- | --- |
| Data folder | `/srv/openwrt-validation/router-audit/` — mode `0700`, inherited ACLs removed (the HDD's default ACLs grant example UIDs 1001/1002 read; keep them off this folder) |
| Database | `router-audit.sqlite` (`0600`), pull.py schema: `batches(id, time, module, payload)`, `state(host, cursor)` |
| Derived cache | `router-audit.sqlite.derived`, created by `analyze.py`; safe to delete (rebuilt incrementally) |
| Scripts | `pull.py`, `analyze.py`, `explain.py`, `mcp_server.py`, `normalize.py`, `schema.json`, `prompts/` — **copies** of `package/custom/router-audit/files/` at `b7cb955d13`; repo edits do not affect them until copied again |
| Units | `~/.config/systemd/user/router-audit-pull.service` (oneshot, `TimeoutStartSec=50`, `UMask=0077`, `Nice=10`, idle I/O) and `router-audit-pull.timer` (`OnCalendar=minutely`), enabled |
| SSH | `~/.ssh/id_ed25519_router_audit` → `router-audit@192.0.2.1`; the router forces `/usr/libexec/router-audit-ssh`, which only allows `router-audit-export ...` read commands |
| History | seeded from the test pull: data from 2026-11-06 09:47 +08 onward. Records before 13:17 are schema 1.0 (r1 collector), later ones 1.1; `normalize.upgrade()` handles both |
| Retention | `pull.py` deletes records older than 30 days; roughly 100–150 MB/day; no disk cap |

Operational facts:

- `Linger=no` for `example-user`: the timer only runs while the user is logged in. The router keeps a
  24-hour spool (256 MiB cap) and the puller resumes from its cursor, so gaps under 24 hours are
  backfilled; longer logged-out periods lose data. Enabling linger was not done (user decision).
- Baseline verdicts need 24 hours of history: expect the first ones around 2026-11-07 09:47 +08,
  and same-hour ±1 comparisons only after several days. Until then every baseline line says
  `no baseline yet`.
- Status and logs: `systemctl --user list-timers router-audit-pull.timer`,
  `journalctl --user -u router-audit-pull.service`. Each run prints `Stored records: N`.
- Stop: `systemctl --user disable --now router-audit-pull.timer`. Deleting the folder discards
  the collected history (the router cannot resend more than 24 hours).
- Updating the scripts: copy the files from `package/custom/router-audit/files/` again (keep
  `prompts/` beside them; the scripts load `normalize.py`, `analyze.py` and `prompts/` from their
  own directory). Do not point the timer at the repository working tree.

## Temporary test workspace (not a deployment)

`/srv/openwrt-validation/router-audit-llm-test-20261106/` (~14 GB) holds everything used for the model
evaluation. Nothing in it is started automatically. Keep it while the analyzer is being built; it
saves re-downloading and holds the evidence for `router-audit-validation.md`.

| Path | Content |
| --- | --- |
| `bin/llama-b12143/` | llama.cpp b12143 prebuilt Vulkan x64 (`llama-server`, `llama-bench`, …), SHA-256 verified |
| `models/` | `Qwen3.5-4B-Q6_K.gguf` (default), `granite-4.2-8b-Q4_K_M.gguf`, `Qwen3.5-9B-Q4_K_M.gguf`, SHA-256 verified (hashes in the validation record) |
| `serve.sh MODEL.gguf ALIAS CTX` | starts `llama-server` on `127.0.0.1:18080` (`-np 1 -ngl 99 -fa on`, q8_0 KV, `--jinja`); run it in the foreground or background and stop it afterwards |
| `fixtures/` | 7-day synthetic fixture databases + `manifest.json` (built by `scripts/tests/router-audit-fixtures.py`) |
| `db/real.sqlite` | the first manual pull (superseded by the permanent database; kept as evidence) |
| `runs/` | every eval report, `results.{json,md}`, server logs, `gpu-bench.jsonl` |
| `fetch.sh`, `final-compare.sh`, `gpu-bench.py`, `gpu-state.sh`, `power-sweep.sh` | download/verify, head-to-head eval, GPU power measurement and sysfs GPU states (`gpu-state.sh reset` restores defaults; its `od` mode needs an overdrive boot option that is **not** set) |

Example session (no install):

```
W=/srv/openwrt-validation/router-audit-llm-test-20261106
$W/serve.sh Qwen3.5-4B-Q6_K.gguf qwen3.5-4b-q6_k 32768 &      # wait for curl -sf 127.0.0.1:18080/health
python3 /srv/openwrt-validation/router-audit/explain.py /srv/openwrt-validation/router-audit/router-audit.sqlite \
	--endpoint http://127.0.0.1:18080/v1 --model qwen3.5-4b-q6_k --window 1h --out /tmp/report
kill %1
```

## Host and GPU facts

- Ryzen 7 5700X3D, 32 GB RAM (often ~12 GB free while OpenWrt builds run), Radeon RX 6600 XT
  (Navi 23, 8 GB VRAM) that also drives the GNOME desktop (~0.8 GB baseline). Vulkan (RADV) works;
  ROCm is not used. Debian kernel 7.2.12, Python 3.14, no `mcp` Python SDK and no LLM runtime
  installed system-wide.
- The GPU is power-limited at 130 W while generating (~118 W average, junction ~102 °C) and idles at
  ~4.9 W with or without a model loaded. Power profiles, clock levels and the 122 W minimum cap
  change energy by at most 2%; lowering the memory clock costs more energy. A finer core-clock cap
  would need `amdgpu.ppfeaturemask` overdrive: it was prepared, then removed by the user's decision
  (no reboot happened). Do not re-add it without asking.
- GPU settings changed through sysfs reset on reboot; the GPU was left at `auto` / 130 W.

## Decisions already made with the user

- Local model: **Qwen3.5-4B Q6_K, thinking off**, budget 4000, `llm` text format, pipeline mode
  (measured best; see the guide and validation record). Thinking mode is not wanted: no accuracy
  gain, 10–30× slower, sometimes no answer. It is excluded from the eval sweep.
- All arithmetic, baselines, thresholds and identity resolution stay in `analyze.py`; the model
  only explains and prioritises. Rule severity stays authoritative.
- The router output stays model-agnostic; model-specific shaping happens only on Debian
  (`analyze.py` renderers, `prompts/`).
- Data is local only: reports contain client addresses, hostnames and DNS names. Keep files
  `0600`/`0700` and do not send them to external services.
- Earlier instruction: test with a real model but **do not formally deploy on Debian**. The minute
  puller is the one approved exception. Ask before adding a model service, explain timer, MCP
  client registration, linger, packages or boot changes.

## Not done yet (scope for the next agent)

- No LLM runtime, model service or schedule for `explain.py` exists outside the test workspace.
- No report storage, notification or UI; `explain.py` only writes `report.json`/`report.md` where
  told.
- Baseline-driven findings have not been seen on real data (history too short).
- Fixtures are synthetic and small: they check that faults are named and nothing is invented, not
  diagnosis quality on unusual real incidents. Real windows so far produced only `info` findings
  (eth1 receive drops, a few conntrack insert failures).
- Periodic beaconing detection, per-client connection accounting and container health are not
  implemented (see the guide's coverage gaps).
- Tool choice is 9/10 for the 4B (it answers "How busy are the CPU and memory?" with the overview);
  agent mode works but is slower than the pipeline.

## Pitfalls seen during this work

- `explain.py` agent mode and `mcp_server.py` load `analyze.py` from their own directory; editing it
  mid-run can mix versions between the client and the MCP subprocess.
- Small models pad lists and relabel copied fields; keep schemas narrow (the summary schema is built
  per window with real finding IDs, each finding schema pins `id` and `category`).
- Real data differs from fixtures: one-shot services, PTR NXDOMAIN, Linux receive-drop counters and
  conntrack insert races all looked like problems until checked. Verify new rules on
  `router-audit.sqlite` before trusting them.
- `pkill -f PATTERN` from a shell whose own command line contains PATTERN kills that shell; prefer
  `pgrep -x llama-server` / `kill PID`.
