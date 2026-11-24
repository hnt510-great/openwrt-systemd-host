# router-audit

Read-only router observability exporter (`/usr/sbin/router-audit-export`),
opt-in bounded minute collector (`router-audit-collect.service`, spool
`/srv/router-audit` <= 256 MiB / 24h, schema `1.1`), and off-router companion
scripts (`/usr/share/router-audit/`).

## Configuration

Background collection is opt-in and disabled by default in
`/etc/config/router-audit`:

```uci
config router-audit 'main'
	option enabled '0'
```

To enable or disable background collection inside a protected `uci-history`
transaction:

```sh
sudo -n uci-history --json begin --timeout 300 --note 'Toggle router-audit collection'
sudo -n uci set router-audit.main.enabled='1'
sudo -n uci commit router-audit
sudo -n /etc/init.d/router-audit reload
sudo -n /etc/init.d/dnsmasq reload
sudo -n /etc/init.d/daed reload
sudo -n uci-history --json confirm
```

## On-router Export Commands

```sh
sudo router-audit-export capabilities
sudo router-audit-export snapshot
sudo router-audit-export system
sudo router-audit-export services
sudo router-audit-export network
sudo router-audit-export identity
sudo router-audit-export firewall
sudo router-audit-export connections
sudo router-audit-export inventory
sudo router-audit-export virtualization
sudo router-audit-export changes --since 24h
sudo router-audit-export incidents --since 1h
sudo router-audit-export dns --since 15m
sudo router-audit-export dns --since 15m --view events --limit 1000
sudo router-audit-export samples --since 15m --limit 500
sudo router-audit-export samples --cursor TOKEN
```

## Companion Off-router Tools (`/usr/share/router-audit/`)

- `pull.py`: incremental SQLite ingestion over the restricted `router-audit` SSH entry.
- `analyze.py`: deterministic rates, 7-day baselines, findings, and text summaries.
- `explain.py`: local OpenAI-compatible LLM explanation runner.
- `mcp_server.py`: read-only stdio MCP server (`router_overview`, `router_finding`, `router_topic`).
- `normalize.py` and `schema.json`: shared schema `1.1` normalizer and output contract.
