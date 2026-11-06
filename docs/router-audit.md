# Router audit

`router-audit` provides JSON snapshots, minute samples and bounded resolver metadata. The router runs one collector; rules, SQLite and optional LLM inference run off-router. It does not modify UCI, firewall rules, routes or credentials. The collector writes only its own spool; fixed network probes generate small amounts of traffic.

## Build and installation

Enable `CONFIG_PACKAGE_router-audit=y` (selected in the desktop snapshot). Build `package/custom/router-audit/compile`, `package/custom/daed/compile` and `package/network/services/dnsmasq/compile`. The daemon releases are bumped for the audit hooks. The init scripts enable hooks only while `/usr/libexec/router-audit` is installed. dnsmasq mounts the audit runtime directory into ujail. No query/debug file logging is enabled.

The package supplies `/usr/sbin/router-audit-export`, `/usr/libexec/router-audit*`, `router-audit-collect.service` and Debian companion scripts under `/usr/share/router-audit/`. Collector activation is intentional for this image. Package removal stops it; DNS forwarding tolerates absent collectors.

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

Schema version is `1.0`. Envelopes contain `host_id` (machine-id digest), `collected_at`, `module`, `status`, `data`, and `errors`. Snapshot modules generally also contain boot ID and window; wrappers and error replies may omit these optional fields. `status=partial` is expected for resolver coverage, bounded journal signatures and history. Missing observations are not zeros.

DNS events contain source, process epoch/sequence, original event time, client, qname, qtype, rcode, cache/duration where available and producer drops. daed timestamps request handling and records handler duration/cache status; dnsmasq records successfully sent responses and cannot provide request start, cache status or upstream latency. RCODE may be null on daed failures; timeout is not SERVFAIL. Do not interpret dnsmasq response counts as all attempted queries. The raw producer epoch/sequence can be used for event deduplication.

Minute DNS windows are collector intervals rather than calendar-aligned buckets. They group observations by source/client, including QTYPE/RCODE counts, unique retained names and maximum length. Internal loopback dnsmasq observations have `internal=true`: exclude them when counting clients to avoid counting daed upstream forwarding twice. Detailed windows are bounded; `truncated` means narrow the request or use sample paging. Snapshot dns metrics are dnsmasq cumulative counters; detailed data is carried by `dns_queries` and `dns_minute` records. DNS observations arrive in the next minute batch.

Client DoH/DoT/DoQ, application caches, uninstrumented namespaces and remote proxy DNS remain gaps. IPv6 neighbor/DHCP identity is a snapshot association, not proof of permanent device ownership. nlbwmon connections are period cumulative, not concurrent. TCX proxying, flow offload and notrack prevent claiming complete per-client connection/traffic accounting.

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

Copy `pull.py` and `analyze.py` from the package's `/usr/share/router-audit/` to the intended analysis directory. For the currently enrolled key:

```
python3 pull.py router-audit@192.0.2.1 --identity ~/.ssh/id_ed25519_openwrt --database router-audit.sqlite
python3 analyze.py router-audit.sqlite > evidence.json
```

Run the puller once a minute using an administrator-managed timer. It commits samples and cursor together, deduplicates batch IDs, and deletes records older than 30 days. SQLite free pages are reused, not automatically vacuumed. No hard Debian disk cap is implemented; monitor storage and adjust retention. The source repository is synchronized to Debian, but no analysis timer or database is installed there automatically.

The analyzer implements basic available-memory, stopped-service, failed-unit, probe-failure and DNS error/unusual-label candidates. It does not yet maintain learned baselines or periodic-C2 detection. Evidence contains facts, candidates, related changes, typed logs, coverage gaps and available bounded module names. Logs are typed signatures rather than raw MESSAGE export. Evidence is for local analysis and is not automatically anonymized for external LLMs: redact client addresses/domains before sending it outside the local environment.

## Disable / rollback

```
systemctl disable --now router-audit-collect.service
```

Nonblocking producers then drop metadata while normal DNS continues. To avoid producer work entirely, remove audit activation from the init scripts or remove the audit package, then restart through `/etc/init.d/daed` and `/etc/init.d/dnsmasq`. Roll back the packages separately if needed. Original production init scripts from initial deployment were backed up on the router under `/srv/openwrt-validation/router-audit/backups`; they are not repository artifacts. Revoke the account's authorized key and sudoers rule to disable SSH audit access. Spool deletion is a separate administrator decision.
