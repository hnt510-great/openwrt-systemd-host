# Plan: make router-audit output usable by a local 4–8B LLM

Status: implemented 2026-11-06 as router-audit 1.0.0-r2 (installed on the router) and r3
(analyzer-only, published). The guide is `docs/router-audit.md`; the validation record
`docs/router-audit-validation.md` has the checks and the measured model comparison;
`docs/router-audit-debian.md` records the Debian host state and the handover for the analyzer build.

Changes beyond this plan, found by running the analyzer on real router data:

- `pull.py` backfills the router's whole 24-hour buffer on its first run (it previously inherited
  the export default of 15 minutes).
- Baseline verdicts need at least 24 hours of history, not just 30 samples.
- Reverse (`*.arpa`) lookups are excluded from DNS error ratios; PTR NXDOMAIN is normal.
- Interface drops are split into receive drops (`info`, Linux counts unhandled-protocol frames
  there) and transmit drops (`warning`).
- procd instances that exited cleanly (`inactive`, status 0, e.g. `urandom_seed`, `acme`) are not
  reported as stopped.
- The collector's DNS receiver thread now survives socket errors.

## Context

Commit `b7ad87dbc3` added `router-audit` (router collector → Debian `pull.py` SQLite →
`analyze.py` evidence packet). The data will be analysed by a **local 4–8B model on this Debian
host**. Reviewing a live minute batch showed the current output does not suit that:

- ~62 KB/min raw (~1M tokens/hour); the evidence packet is JSON with nested raw data.
- **Bug:** daed reports `client` as `IP:port`; the port changes per query, so `dns_minute` showed
  25 "clients" (23 daed with 1–2 queries each) and `dns_error_ratio` (≥30 obs/client) never fires.
- Only cumulative counters (cpu ticks, link stats64, nft, conntrack, wg) — no rates.
- Text blobs inside JSON (`systemctl show` Key=Value, hex per-CPU conntrack table, `/proc`
  pressure lines, `virsh`/`ps` tables); nft rules lack their fw4 `comment`; five timestamp formats.
- No baselines, so "is this value normal?" is left to the model.

**Layering (decided after the 2026 model review):**

- **Router output stays model-agnostic.** The service emits complete, structured, lossless
  machine data. Its schema 1.1 changes fix correctness and parseability (daed port bug, text
  blobs, missing nft comments, mixed timestamps) and would be needed for *any* consumer. The
  router never gets verdicts, prose, hostname substitution or LLM-sized summaries: models change
  every few months, router releases need a build + publication + router preflight.
- **The LLM view is rendered on Debian** (`analyze.py` renderers + `prompts/`), so it can be
  re-tuned for each new model generation without touching the router.
- **Arithmetic stays in code even though 2026 models are better.** Qwen3.5-class 4B models do
  well on reasoning benchmarks only in thinking mode with very long outputs; exact rates,
  7-day baselines and thresholds are cheap, exact and testable in Python, and baselines are
  facts the model cannot infer from one snapshot anyway.
- **What 2026 capability relaxes:** longer usable context (262k native, AA-LCR 57 for the 4B)
  and decent multi-turn tool use (TAU2 ~80) — so the token budget, text-vs-JSON format and
  pipeline-vs-agent mode become eval parameters instead of fixed limits.

## Model / context decision (for this host)

Host: Ryzen 7 5700X3D (8C/16T, AVX2), 32 GB RAM (often ~12 GB free during builds),
Radeon RX 6600-class (Navi 23, 8 GB VRAM, also drives the desktop).

### Model selection (web research, 2026-11-06; vendor numbers, protocols differ)

What matters here: instruction following + schema-constrained JSON, reading ~3k tokens of
digested text, 2–3 tool calls, a usable non-thinking mode, fits 8 GB VRAM shared with the
desktop, mature llama.cpp support, Apache-2.0.

| Model | Size / GGUF | IF | Tool use | Notes |
|---|---|---|---|---|
| **Qwen3.5-4B** (Mar 2026) | 4B, Q6_K ≈ 3.5 GB | IFEval 89.8, IFBench 59.2 | BFCL-V4 50.3–55.7, TAU2 79.9 | Best ≤5B on AA index; hybrid DeltaNet → KV ≈ 0.5 GB @16k; thinking off via `enable_thinking=false` |
| **Granite 4.2 8B** (Aug 2026) | 8B dense, Q4_K_M ≈ 5 GB | IFBench 79.3 | BFCL-V4 52.4, τ³ 58.1 | Tool-calling focus, RULER 128K 71; dense GQA → KV ≈ 1.3 GB @16k q8 |
| **Qwen3.5-9B** (Mar 2026, 1B over range) | 9B, Q4_K_M ≈ 5.7 GB | IFEval 91.5, IFBench 64.5 | BFCL-V4 66.1, TAU2 79.1 | Strongest <10B; AA-LCR 63; tight but fits at 16k |
| K2 Horizon 3.7B (Oct 2026) | 3.7B | IFEval 83.7 (80.4 at Q4) | BFCL-V4 50.9 | Reasoning-only, needs llama.cpp ≥ b11454 + custom parsers → not chosen |
| Gemma 4 E4B (Mar 2026) | 8B total / 4.5B eff., ~6 GB | IFBench 44 | Tau2 42.2 | Clearly behind Qwen3.5-4B → not chosen |
| Nemotron 3 Nano 4B | 4B | IFEval 82.8 (no-think) | BFCL-V4 36.8 | NVIDIA licence, weaker tools → not chosen |

**Choice:** default **Qwen3.5-4B Q6_K, non-thinking** (best quality per GB, leaves VRAM free, ~2×
faster). The live test also runs **Granite 4.2 8B Q4_K_M** (in-range 8B challenger) and
**Qwen3.5-9B Q4_K_M** (stretch); the eval fixtures, not leaderboards, decide. Q6_K for the 4B
because Q4 measurably hurts small models (K2 card: IFEval −3, GPQA −10 at Q4_K_M).

- **Context: 32k for Qwen3.5** (hybrid attention → KV ≈ 1 GB at 32k), **16k for Granite**
  (dense KV). Data budget per prompt is a `--budget` option (chars/4 estimate), **default 4k
  tokens**, evaluated at 3k / 8k / 16k; the smallest budget that scores within noise of the
  best becomes the default (prompt processing time grows with it).
- Non-thinking is the default for per-finding JSON calls; the eval measures thinking mode too.
  Latency matters little (analysis runs every 15 min or on trigger, not per minute), so thinking
  may win for the summary step.
- Runtime undecided → target only the generic OpenAI-compatible `POST /v1/chat/completions`
  with `response_format: json_schema` (llama.cpp server, Ollama `/v1`, LM Studio, vLLM all accept
  it); fallback `json_object` + local validation + one retry. Docs note that llama.cpp's Vulkan
  backend runs on Navi 23 without ROCm overrides (host has `libvulkan.so.1` + RADV ICD).
- **Testing uses a real model, but nothing is deployed on Debian** (see "Live model test").

## Changes

### 1. Collector at source — `package/custom/router-audit/files/router-audit` (schema 1.1)

Correctness/structure only, no LLM shaping (see Layering). Keeps raw counters; no rates,
verdicts or hostnames on the router.

- Receiver normalizes DNS `client` to the address (strip `:port`, `[]`, `::ffff:`), keeps
  `client_port`. **daed patch untouched**, no daed rebuild.
- Structured fields: `system.memory` (selected meminfo keys), `system.cpu` (parsed ticks),
  `system.pressure` (`{cpu|memory|io:{some|full:{avg10,avg60,avg300,total}}}`),
  `services.systemd` (list of dicts), `services.failed` (unit names), `firewall.rules[].comment`
  (drop rules with neither counters nor comment), `conntrack_stats` summed across CPUs,
  `network.links` without `lo`, parsed `virtualization` lists.
- One `iso()` helper → ISO-8601 UTC `Z` for every timestamp.
- Journal events gain `detail`: the matched pattern text only (≤120 chars), not the MESSAGE.
- `schema_version` 1.1 (`schema.json` accepts 1.0/1.1); `PKG_RELEASE:=2` in the Makefile.
- Parsers live in new stdlib `files/normalize.py`, installed to
  `/usr/libexec/router-audit-normalize.py` (collector loads it via `SourceFileLoader`) and
  `/usr/share/router-audit/normalize.py` (Debian scripts import it) — one implementation.

### 2. Deterministic analysis — rewrite `files/analyze.py` (stdlib, importable)

- `load()` reads `batches`, normalizes 1.0 records to 1.1 via `normalize.py`.
- `rates()`: per-sample deltas reset on `boot_id` change or counter decrease — CPU %, iface
  rx/tx bit/s + errors/drops per min, conntrack used %, insert_failed/drop per min, nft rule
  rates (by comment), wg transfer rates, service restart increments.
- `baselines()`: median and p95 of each key metric over the previous 7 days, overall and same
  hour ±1 (SQLite keeps 30 days). Verdict `normal | high | unusual` vs p95 / 3× median.
- `identity()`: map IP/MAC → DHCP hostname (dhcp4, dhcp6, neighbours) so text says
  `laptop (192.0.2.23)` instead of addresses/MACs.
- DNS per client (internal loopback excluded): queries, NXDOMAIN/SERVFAIL %, unique and
  never-seen-in-7-days domains, high-entropy-label count, top-5 registrable domains (last two
  labels, three for a small built-in list such as `com.cn`, `co.uk`; documented approximation).
- `findings()`: existing rules plus conntrack ≥80 %, iface error/drop rate, insert_failed > 0,
  PSI memory avg60 > 10, restart increases, DNS producer/receiver drops, metric `unusual` vs
  baseline, coverage gaps (missing minutes, `cursor_expired`). Each finding: short ID (`F1`…),
  category enum, rule-assigned severity, and a context block (±5 min WAN state, related journal
  `detail`s, UCI changes, the metric's baseline).
- Renderers:
  - `--format json`: machine form (all of the above).
  - `--format llm` (default for the LLM path): plain-text, flat `key: value` lines; every number
    carries unit, verdict and threshold (`conntrack: 41% of max — OK (warn ≥80%)`); times as
    local `HH:MM` plus "N min ago"; no hashes, boot/host IDs; only the coverage gaps relevant to
    each finding. Sections: `OVERVIEW` (findings listed by ID) and one `FINDING Fn` block each.
  - `--format llm-json`: the same content as compact JSON (eval A/B against text).
  - `--budget TOKENS` scales detail instead of only truncating: top-N lists (5 → 20), and at
    ≥8k a short per-10-minute series for the finding's metric. Hard limit kept, with an explicit
    `[truncated: N more]` line.

### 3. Local model runner — new `files/explain.py` (stdlib `urllib`)

- `explain.py DB --endpoint http://127.0.0.1:8080/v1 --model NAME [--hours 1] [--max-findings 8]`.
- Map step: one request per finding (system prompt + one worked example + that finding block),
  `temperature 0.2`, fixed seed, answer constrained by `prompts/finding.schema.json`:
  `{id, severity: enum, category: enum, explanation ≤300 chars, likely_causes[≤3],
  next_checks[≤3], confidence: low|medium|high}`. Invalid JSON → one retry, then record
  `model_error` rather than guessing.
- Reduce step: one request with `OVERVIEW` + the short per-finding verdicts → top-3 summary.
- `--mode pipeline` (default, above) or `--mode agent`: the model gets `OVERVIEW` plus the three
  MCP tools (via the OpenAI `tools` parameter, executed against `mcp_server.py`) and may make up
  to 6 calls before giving the same schema-constrained summary. Agent mode is kept only if the
  eval shows it beats the pipeline on this hardware.
- `--budget`, `--format`, `--think on|off` pass through, for the eval matrix.
- Output: `report.json` + `report.md`. Rule severity stays authoritative; the model's severity
  is shown beside it, never replaces it.
- Prompt files in `files/prompts/` (`system.txt`, `example.txt`, `finding.schema.json`,
  `summary.schema.json`) so they can be tuned without code changes; `--extra-system` for
  model-specific switches (e.g. disabling thinking mode).

### 4. Tiny MCP server — new `files/mcp_server.py` (stdlib, stdio JSON-RPC)

`initialize`, `tools/list`, `tools/call`, `ping`; read-only SQLite. Three tools, flat enum
params, one-line descriptions, each returning the `--format llm` text (≤ 3k tokens):

| Tool | Params |
|---|---|
| `router_overview` | `window: "1h" \| "6h" \| "24h"` |
| `router_finding` | `id: "F1".."F99"`, `window` |
| `router_topic` | `topic: system \| wan \| dns \| clients \| conntrack \| services \| firewall \| changes \| logs`, `window` |

### 5. Smaller items

- `pull.py`: `CREATE INDEX IF NOT EXISTS batches_module_time ON batches(module,time)`.
- Makefile installs `normalize.py`, `explain.py`, `mcp_server.py`, `prompts/`.
- `docs/router-audit.md`: schema 1.1, client semantics, LLM-path design, hardware/context
  guidance above, `explain.py` and MCP setup. `docs/router-audit-validation.md`: dated r2 section.

## Tests

New `scripts/tests/router-audit-fixtures.py` builds synthetic SQLite DBs (schema 1.0 and 1.1
records, 7 days of baseline + 1 test hour) with one injected fault each: WAN flap (down/up events
+ probe failures), conntrack 90 %, NXDOMAIN storm from one client, high-entropy labels from one
client, failed unit + restart increments, memory pressure — plus a **quiet** fixture with no fault
(the model must not invent issues). Used by the unit tests and the live model eval.

### Unit — `scripts/tests/test-router-audit.py` (no router, no model)

- Client normalization (`192.0.2.1:123`, `[2001:db8::1]:53`, `::ffff:192.0.2.1`, loopback);
  two daed ports → one client.
- Parsers: systemd blocks, conntrack hex sum over 2 CPUs, PSI, nft comment kept, `iso()`.
- analyze: 1.0→1.1 normalization; rates across boot_id/counter reset; baseline verdicts;
  hostname substitution; registrable-domain approximation; each injected fault yields its finding.
- Budget: `--format llm` for a synthetic busy 1-hour DB stays within the char limits.
- explain.py against a stdlib `http.server` fake endpoint: valid answer, invalid-then-valid
  retry, invalid twice → `model_error`; `json_object` fallback when `json_schema` is rejected.
- MCP: drive `mcp_server.py` over stdio — initialize, tools/list, each tool, bad enum rejected.

### Live model eval — new `scripts/tests/router-audit-llm-eval.py` (needs `--endpoint`, else skips)

- Findings: run `explain.py` on every fixture; score valid-JSON rate, category match, severity
  within one level of the rule, and zero findings invented on the quiet fixture.
- Matrix per model (kept small, ~7 fixtures each): budget 3k/8k/16k × format text/llm-json ×
  think off/on × mode pipeline/agent — run as a one-factor-at-a-time sweep from the default
  (4k, text, off, pipeline), not the full product. Records score, wall time, tokens.
- Tools: give the model the three MCP tool schemas via the OpenAI `tools` parameter, execute its
  calls against `mcp_server.py` over stdio, and check it picks the right tool/params for ~10
  scripted questions ("is the WAN stable?", "which client has DNS errors?", …).

## Live model test (temporary, not a deployment)

Everything lives in a dated workspace outside the repo, following the evidence convention:
`/srv/openwrt-validation/router-audit-llm-test-20261106/` (`bin/`, `models/`, `db/`, `runs/`).

- Runtime: llama.cpp **prebuilt** Vulkan release zip from GitHub (no `glslc` on the host to
  build it), unpacked into `bin/`, checksum recorded. CPU-only binary (AVX2) as fallback if
  Vulkan fails.
- Models: Qwen3.5-4B Q6_K, Granite 4.2 8B Q4_K_M, Qwen3.5-9B Q4_K_M (text weights only, no
  vision projector), from the publisher's official GGUF repo or a well-known quantizer
  (Unsloth/bartowski) with the fixed Qwen3.5 tool-call template; SHA-256 checked against the
  Hugging Face metadata, stored in `models/` (~15 GB on the HDD).
- `llama-server` started by hand for the test run only, bound to `127.0.0.1` on a free port,
  `-c 32768` (Qwen3.5) / `-c 16384` (Granite), `-ngl 99 --cache-type-k q8_0 --cache-type-v q8_0
  --jinja`; stopped afterwards.
- **No** apt packages, systemd/user units, autostart, PATH or shell-profile changes, MCP client
  registration or timers. Removing the workspace directory removes everything.
- Data: fixture DBs plus one real DB pulled into `db/` with the existing enrolled read-only key
  (`pull.py` read-only SSH entry); not stored in the repo.
- Recorded in `docs/router-audit-validation.md`: llama.cpp build, model names + SHA-256, VRAM
  use, prompt/generation tok/s, per-fixture eval scores for 4B vs 8B, one example report from
  the real DB (client addresses replaced by hostnames already; no domains quoted in the doc).

## Verification

1. `python3 scripts/tests/test-router-audit.py`; `git diff --check`.
2. `make package/custom/router-audit/compile V=s`.
3. On the workspace DB copy: `analyze.py --format llm` (daed clients grouped by host, sizes
   within budget) and `--format json`.
4. Live model test above: `router-audit-llm-eval.py --endpoint http://127.0.0.1:PORT/v1` for each
   of the three models (non-thinking, plus one thinking pass); `explain.py` on the real DB with the
   winner. Then stop `llama-server`. Record the winning model, budget, format, thinking and mode
   as the documented defaults.
5. Publishing router-audit r2 and installing it on the router only when the user authorizes
   (`./scripts/publish-changed-feeds.sh --dry-run` first).

## Out of scope

daed patch changes, periodic-C2 detection, permanently installing an LLM runtime or MCP client on
Debian, Debian timers/services.

## Sources (model research, retrieved 2026-11-06)

Benchmark figures are vendor-reported unless noted; evaluation protocols differ between cards.

- Qwen3.5-4B model card: https://huggingface.co/Qwen/Qwen3.5-4B
- Artificial Analysis, Qwen3.5 small models: https://artificialanalysis.ai/articles/qwen3-5-small-models
- Artificial Analysis, tiny open models: https://artificialanalysis.ai/models/open-source/tiny
- Artificial Analysis, sub-32B open weights: https://artificialanalysis.ai/articles/sub-32b-open-weights
- Granite 4.2 8B model card: https://huggingface.co/ibm-granite/granite-4.2-8b
- Gemma 4 E4B model card: https://huggingface.co/google/gemma-4-E4B-it
- Gemma releases: https://ai.google.dev/gemma/docs/releases
- K2-Horizon-3.7B GGUF card: https://huggingface.co/IFM/K2-Horizon-3.7B-GGUF
- Nemotron 3 Nano 4B model card: https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16
- Small LLMs that fit in 8 GB (2026-09-15): https://pinggy.io/blog/small_llms_that_fit_in_8gb_memory/
- October 2026 model updates: https://local-ai-zone.github.io/blog/October_2026_AI_Model_Updates.html
- Unsloth Qwen3.5 run guide (tool-call template fix): https://unsloth.ai/docs/models/qwen3.5
