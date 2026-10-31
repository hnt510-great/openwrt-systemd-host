# ttyd over HTTPS validation

Validated on 2026-11-01 against the physical router at `192.0.2.1`
(LuCI on uhttpd `:443` with the ACME certificate for `router6.example.invalid`).
The packaged change was built but **not published or installed**; the router
received only the equivalent manual UCI hotfix. No image was built or flashed
and the router was not rebooted.

## Artifacts

| Package | SHA256 |
| --- | --- |
| `ttyd-1.7.7-r4.apk` | `7d79abe47748816dc09ff5068d935e864ab5475cfdb6e3a88e940c09c9b64853` |
| `luci-app-ttyd-26.304.59848~fce3f1d.apk` | `00ff2c9e16ec582ea754ce7e6824ba9b7d5c242f9d3696d19b38da684e65a600` |

## Checks

| Check | Result |
| --- | --- |
| Cause | ttyd had no `ssl`; LuCI view embedded `http://…:7681` in an HTTPS page |
| `sh -n` on init, uci-defaults and hotplug scripts | Pass |
| `node --check` on `term.js` | Pass |
| `make package/feeds/packages/ttyd/compile` | Pass; payload contains `80-ttyd-https` and `hotplug.d/acme/50-ttyd` |
| `make package/feeds/luci/luci-app-ttyd/compile` | Pass |
| Release identity | `r4`; `r1`/`r2` map to the published `r3` in `configs/apk-elf-rebuilds.mk` |
| Router hotfix | `ssl=1` with ACME cert/key; backup `/etc/config/ttyd.bak-20261101` |
| ttyd after restart | `-S -C …fullchain.crt -K …key`, "Vhost 'default' using TLS mode", cert expiry 74 days |
| `https://router6.example.invalid:7681/` from the LAN host | HTTP 200, certificate verified |
| `https://192.0.2.1:7681/` (verification skipped) | HTTP 200 |
| `http://192.0.2.1:7681/` | 301 |

Not checked: rendering in a browser, ACME renewal reload, and installation of
the packaged uci-defaults on the router.

**Evidence:** command output in the session on 2026-11-01; build logs were
kept in a temporary scratch directory only.
