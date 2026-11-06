# Router audit

`router-audit` provides JSON snapshots, minute samples and bounded resolver metadata. The router runs one collector; rules, SQLite and optional LLM inference run off-router. It does not modify UCI, firewall rules, routes or credentials. The collector writes only its own spool; fixed network probes generate small amounts of traffic.

## Build and installation

Enable `CONFIG_PACKAGE_router-audit=y` (selected in the desktop snapshot). Build `package/custom/router-audit/compile`, `package/custom/daed/compile` and `package/network/services/dnsmasq/compile`. The daemon releases are bumped for the audit hooks. The init scripts enable hooks only while `/usr/libexec/router-audit` is installed. dnsmasq mounts the audit runtime directory into ujail. No query/debug file logging is enabled.

The package supplies `/usr/sbin/router-audit-export`, `/usr/libexec/router-audit*` (including the shared parser module `router-audit-normalize.py`), `router-audit-collect.service` and Debian companion scripts and prompts under `/usr/share/router-audit/`. Collector activation is intentional for this image. Package removal stops it; DNS forwarding tolerates absent collectors.

## Commands

```
sudo router-audit-export capabilities
sudo router-audit-export snapshot
sudo router-audit-export system
sudo router-audit-export services
sudo router-audit-export network
sudo router-audit-export identity
sudo router-audit-export firewall
sudo router-audit-export inventory
sudo router-audit-export virtualization
sudo router-audit-export changes --since 24h
sudo router-audit-export incidents --since 1h
sudo router-audit-export dns --since 15m
sudo router-audit-export dns --since 15m --view events --limit 1000
sudo router-audit-export samples --since 15m --limit 500
sudo router-audit-export samples --cursor TOKEN
```

`--since` accepts positive m/h/d durations up to 30d. Cursor paging is implemented on `samples`, the persistent transport used by the puller. Other views are bounded queries; `--limit` is 1–1000. JSONL currently emits one complete envelope per invocation, not individual nested events. Errors and unavailable fields remain explicit. `snapshot` modules have separate collection times and are not atomic. Root access is required for privileged live sources; use the restricted SSH entry for remote access.

## Data contract

Schema version is `1.1` (router-audit r2); `1.0` records from r1 spools remain readable. Envelopes contain `host_id` (machine-id digest), `collected_at`, `module`, `status`, `data`, and `errors`. Snapshot modules generally also contain boot ID and window; wrappers and error replies may omit these optional fields. `status=partial` is expected for resolver coverage, bounded journal signatures and history. Missing observations are not zeros.

DNS events contain source, process epoch/sequence, original event time, client, qname, qtype, rcode, cache/duration where available and producer drops. daed timestamps request handling and records handler duration/cache status; dnsmasq records successfully sent responses and cannot provide request start, cache status or upstream latency. RCODE may be null on daed failures; timeout is not SERVFAIL. Do not interpret dnsmasq response counts as all attempted queries. The raw producer epoch/sequence can be used for event deduplication.

Minute DNS windows are collector intervals rather than calendar-aligned buckets. They group observations by source/client, including QTYPE/RCODE counts, unique retained names and maximum length. Internal loopback dnsmasq observations have `internal=true`: exclude them when counting clients to avoid counting daed upstream forwarding twice. Detailed windows are bounded; `truncated` means narrow the request or use sample paging. Snapshot dns metrics are dnsmasq cumulative counters; detailed data is carried by `dns_queries` and `dns_minute` records. DNS observations arrive in the next minute batch.

Client DoH/DoT/DoQ, application caches, uninstrumented namespaces and remote proxy DNS remain gaps. IPv6 neighbor/DHCP identity is a snapshot association, not proof of permanent device ownership. nlbwmon connections are period cumulative, not concurrent. TCX proxying, flow offload and notrack prevent claiming complete per-client connection/traffic accounting.

### Schema 1.1 changes

1.1 fixes correctness and parseability only; the router output stays model-agnostic and carries raw counters, never rates, verdicts or hostnames. The same parsers (`normalize.py`) run on the router and on Debian, where `normalize.upgrade()` converts 1.0 records on read and marks them `upgraded_from: "1.0"`.

| Field | 1.0 | 1.1 |
| --- | --- | --- |
| DNS `client` | daed sent `IP:port`, so every query looked like a new client | address only (port stripped, `[]` and `::ffff:` removed); `client_port` kept separately |
| `system.memory` | `memory_bytes`: all of `/proc/meminfo` | selected keys (MemTotal, MemAvailable, Swap*, Shmem, Slab, Dirty, …) |
| `system.cpu`, `system.pressure` | raw `/proc/stat` line, raw PSI text | tick counters; `{cpu\|memory\|io: {some\|full: {avg10, avg60, avg300, total}}}`; plus `cpu_count` |
| `services.systemd`, `services.failed` | `systemctl` text | list of property dicts; list of unit names |
| `firewall.rules` | `{family, table, chain, handle, counters}` | adds the fw4 `comment`; rules with neither counter nor comment are dropped |
| `firewall.conntrack`, `conntrack_stats` | strings; hex table per CPU | integers; counters summed across CPUs |
| `network.links` | every field including `lo` | `lo` removed; `ifname, operstate, mtu, master, link_type, stats64` |
| `virtualization` | `virsh`/`ps` tables | parsed lists |
| journal events | `event_time_us` string | `event_time` ISO; `detail` = the matched signature text only (≤120 chars), never the MESSAGE |
| timestamps | ISO with `Z`, ISO with `+00:00`, epoch, epoch µs | ISO-8601 UTC with `Z` everywhere |

The DNS receiver thread also survives socket errors now instead of silently stopping.

## Storage and resources

The collector uses Nice=19, CPUWeight=10, IOWeight=10 and MemoryMax=128M. Fixed TCP443 probes to IPv4/IPv6 Cloudflare addresses and UDP DNS to 223.5.5.5 run once per minute, each with a two-second timeout. Their path is `system_default`; transparent proxy processing may apply. No ICMP loss measurement or HTTPS application-health claim is made.

The spool is `/srv/router-audit`, root-only, at most 256 MiB and 24 hours for all samples in this implementation. Whole oldest batches are removed; long-offline clients may receive `cursor_expired`. It does not guarantee 24 hours at high DNS volume. Source sockets are nonblocking. The receiver accepts only root/dnsmasq SCM_CREDENTIALS, caps its queue at 10,000 events and exposes receiver/producer drops. No per-query fsync, no crash-durability guarantee. Existing persistent journald and UCI history stay authoritative.

System/network/service/firewall/identity snapshots and typed journal signatures run every minute. Inventory is hourly and virtualization every 15 minutes. Journal scans overlap two minutes and are limited to 1000 records: deduplicate typed events by event ID, and inspect `possible_truncation`. High journal volume can leave gaps. UCI diff uses Git read-only plumbing and the existing parser without constructing History; only allowlisted values are exported. Other values are redacted. Non-UCI metadata is hourly and must be compared between inventories; actor attribution is not available. Container monitor presence is not Podman health.

## SSH enrollment

The physical router has an enrolled `router-audit` account. Personal keys are deliberately not stored in this repository. On a new device create a locked-password account with a valid `/bin/sh` shell and a root-controlled home, then install the approved public key with:

```
restrict,command="/usr/libexec/router-audit-ssh" ssh-ed25519 PUBLIC_KEY
```

Use `.ssh/authorized_keys` in that home. The package's sudoers rule permits only `/usr/libexec/router-audit-read`; the wrapper refuses collector mode and the parser limits commands. No interactive shell, arbitrary sudo command, forwarding or raw configuration export is offered. Keep the SSH key file and installed wrappers root-owned. Enrolling a public key grants router audit data access and is an administrative step.

## Debian companion (manual deployment)

Copy the scripts and `prompts/` from the package's `/usr/share/router-audit/` to the intended analysis directory (they load `normalize.py` and each other from their own directory). For the currently enrolled key:

```
python3 pull.py router-audit@192.0.2.1 --identity ~/.ssh/id_ed25519_openwrt --database router-audit.sqlite
python3 analyze.py router-audit.sqlite > evidence.json
python3 analyze.py router-audit.sqlite --format llm --window 1h
```

Run the puller once a minute using an administrator-managed timer. Its first run backfills the router's whole 24-hour buffer; later runs continue from the stored cursor. It commits samples and cursor together, deduplicates batch IDs, and deletes records older than 30 days. SQLite free pages are reused, not automatically vacuumed. No hard Debian disk cap is implemented; monitor storage and adjust retention. The source repository is synchronized to Debian, but no analysis timer, database, model runtime or MCP client is installed there automatically. The current state of this Debian host (a user-level minute puller and its database, the model test workspace) and the handover notes for building the local analyzer are in `router-audit-debian.md`.

### Deterministic analysis (`analyze.py`)

All arithmetic happens in code so that a small model only explains:

- **Rates** from counters (CPU %, interface bit/s, errors and drops per minute, conntrack drops, nft rule rates by fw4 comment, WireGuard transfer, restart increments), reset on reboot or counter decrease.
- **Baselines**: median and p95 over the previous 7 days, same hour ±1 when there are enough samples. A verdict needs at least 24 hours of history; until then the view says `no baseline yet`. `high` means above p95, `unusual` means above p95 and 3× the median by more than a per-metric floor.
- **Identity**: client addresses are shown with their DHCP hostname (`laptop (192.0.2.10)`), IPv6 included through neighbour MACs.
- **DNS per client** (loopback forwarding excluded): queries, NXDOMAIN/SERVFAIL share, registrable domains (last two labels, three for common second-level suffixes such as `com.cn`; an approximation), domains new this window, high-entropy names. Reverse (`*.arpa`) lookups are counted separately and kept out of error ratios because PTR lookups for unnamed addresses normally return NXDOMAIN.
- **Findings** with rule-assigned severity and category: low memory, memory pressure, OOM, WAN interruption, probe failures, conntrack use, and conntrack loss (a warning for any early drop or 100+ insert failures per hour, otherwise info; `drop` counts the packets of the same insert failures), interface errors and transmit drops (warning) or receive drops (info: Linux also counts frames for unhandled protocols), failed units, restarts, instances that stopped without a clean exit (one-shot instances that exit with status 0 are not reported), DNS error ratio, random-looking names, repeated authentication failures, kernel warnings, `unusual` baselines, and coverage gaps or DNS metadata drops.

Per-minute samples are cached in a sidecar SQLite file (`DATABASE.derived`, `--cache PATH|none`), updated incrementally; the source database is opened read-only.

| Option | Meaning |
| --- | --- |
| `--window 15m\|1h\|6h\|24h` or `--hours N` | window ending at the newest record (`--end ISO` to pin it) |
| `--format json` | machine form: state, findings with context, DNS clients, traffic, firewall top rules, changes, events |
| `--format llm` | short plain text: an `OVERVIEW` and one `FINDING Fn` block each; every number carries unit, verdict and threshold; local times with "N min ago"; no hashes or IDs |
| `--format llm-json` | the same content as compact JSON |
| `--budget TOKENS` | size of each block (chars/4 estimate, default 4000); larger budgets show longer top-N lists and, from 8000, a 10-minute series for the finding's metric |
| `--finding F2`, `--topic dns` | one block (topics: system, wan, dns, clients, conntrack, services, firewall, changes, logs) |

The analyzer does not yet detect periodic beaconing. Logs are typed signatures rather than raw MESSAGE export. Output is for local analysis and is not anonymized: keep client addresses and domains inside the local environment.

### Local model (`explain.py`) and MCP tools (`mcp_server.py`)

`explain.py` talks only to an OpenAI-compatible `POST /v1/chat/completions` endpoint (llama.cpp `llama-server`, Ollama `/v1`, LM Studio, vLLM). It never starts a server.

```
python3 explain.py router-audit.sqlite --endpoint http://127.0.0.1:8080/v1 --model NAME --window 1h --out report/
```

- `--mode pipeline` (default): one request per finding (system prompt, one worked example, the finding block) with the answer constrained by `prompts/finding.schema.json` (`severity`, `category`, `explanation`, up to 3 `likely_causes` and `next_checks`, `confidence`), then one summary request (`prompts/summary.schema.json`: `overall`, `summary`, up to 3 `top_issues`).
- `--mode agent`: the model gets the overview plus the three MCP tools and may make up to 6 calls before the same schema-constrained summary.
- Answers use `response_format: json_schema`; a server that rejects schemas gets `json_object` with the schema described in the prompt. Every answer is validated locally; an invalid answer is retried once, then recorded as `model_error` instead of guessed. The rule severity stays authoritative and the model's severity is shown beside it.
- `--think on|off` sets `chat_template_kwargs.enable_thinking` (Qwen3.5, Granite 4.2); `--extra-system TEXT` appends model-specific instructions. Prompts live in `prompts/` and can be tuned without code changes.
- Output: `report.json` (settings, answers, per-call tokens, tok/s and timings) and `report.md`.

`mcp_server.py --database router-audit.sqlite` is a read-only stdio MCP server (JSON-RPC 2.0, no SDK dependency) with three tools sized for small models: `router_overview(window)`, `router_finding(id, window)` and `router_topic(topic, window)`, each returning the `llm` text (3000-token budget by default). Register it with any MCP client, for example `claude mcp add router-audit -- python3 /path/mcp_server.py --database /path/router-audit.sqlite`; nothing registers it automatically.

#### Model guidance for this Debian host

The analysis host has an RX 6600-class GPU (8 GB VRAM, also driving the desktop), a Ryzen 7 5700X3D and 32 GB RAM. The design and the 2026 model comparison are in `docs/router-audit-llm-plan.md`; the measured comparison is in `docs/router-audit-validation.md`.

Measured on 2026-11-06 with llama.cpp b12143 (Vulkan) on identical code (`docs/router-audit-validation.md`):

| Model (GGUF) | Fixture score | Tool choice | Generation | VRAM incl. desktop |
| --- | --- | --- | --- | --- |
| **Qwen3.5-4B Q6_K** (default) | 100% | 9/10 | 56 tok/s | 4.8 GB |
| Granite 4.2 8B Q4_K_M | 100% | 8/10 | 42 tok/s | 7.1 GB |
| Qwen3.5-9B Q4_K_M | 100% | 8/10 | 41 tok/s | 6.4 GB |

Use **Qwen3.5-4B Q6_K with thinking off**, budget 4000, `llm` text, pipeline mode. The larger models were no more accurate on these tasks, were about 40% slower and left little VRAM. Thinking mode gave no accuracy gain at 10–30× the time and, on the 4B, sometimes ran out of tokens before the JSON answer; it stays off. Agent mode matched the pipeline at 1.5–2× the time and 3–8× the input tokens; it is kept for interactive drill-down, not for scheduled reports. Larger budgets (8k/16k) and `llm-json` did not help.

A suitable temporary server (127.0.0.1 only):

```
llama-server -m Qwen3.5-4B-Q6_K.gguf -c 32768 -np 1 -ngl 99 -fa on \
	--cache-type-k q8_0 --cache-type-v q8_0 --jinja --host 127.0.0.1 --port 8080
```

Use a GGUF whose chat template carries the fixed Qwen3.5 tool-call template (for example Unsloth's). The GPU idles at about 5 W with or without the model loaded and draws about 120 W (its 130 W limit) while generating; a report for a window without findings takes about 2 s, one with several findings 10–25 s. GPU power profiles, clock levels and the 122 W minimum cap changed energy per report by at most 2% (answers were identical), and a lower memory clock cost more energy than it saved. Nothing in this repository installs a model runtime, model or service on Debian.

## Disable / rollback

```
systemctl disable --now router-audit-collect.service
```

Nonblocking producers then drop metadata while normal DNS continues. To avoid producer work entirely, remove audit activation from the init scripts or remove the audit package, then restart through `/etc/init.d/daed` and `/etc/init.d/dnsmasq`. Roll back the packages separately if needed. Original production init scripts from initial deployment were backed up on the router under `/srv/openwrt-validation/router-audit/backups`; they are not repository artifacts. Revoke the account's authorized key and sudoers rule to disable SSH audit access. Spool deletion is a separate administrator decision.
