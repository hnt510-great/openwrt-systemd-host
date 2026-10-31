# ttyd terminal over HTTPS

LuCI's *Services → Terminal* page (`luci/admin/services/ttyd`) embeds ttyd in
an iframe. When LuCI is served over HTTPS, browsers silently block an
`http://` ttyd frame as mixed content, leaving a blank page. This fork serves
ttyd over TLS with the same certificate as LuCI.

## Behaviour

- `ttyd` (`feeds/packages/utils/ttyd`, `1.7.7-r4`): with `ssl=1` and no
  `ssl_cert`/`ssl_key`, the init script uses `uhttpd.main.cert` and
  `uhttpd.main.key`. If neither file exists it logs a warning and serves plain
  HTTP. The certificate files are tracked by procd, so `reload` restarts ttyd
  when they change; uhttpd configuration changes also trigger a reload.
- `/etc/uci-defaults/80-ttyd-https` sets `ssl=1` on install/upgrade for ttyd
  sections without an explicit `ssl` value, but only when uhttpd has
  `listen_https`. An explicit `option ssl '0'` is kept.
- `/etc/hotplug.d/acme/50-ttyd` reloads ttyd after an ACME `renewed` or
  `issued` event.
- `luci-app-ttyd`: the view warns when an HTTPS page would embed an `http://`
  terminal, and always shows a link that opens the terminal in a new tab.

## Host names and certificates

ttyd presents the LuCI certificate (here the ACME certificate for
`router6.example.invalid`). Opening LuCI by that name shows the terminal
directly. Opening LuCI by `https://192.0.2.1` already needs a certificate
exception; Firefox stores exceptions per host and port, so accept
`https://192.0.2.1:7681` once through the "Open the terminal in a new tab"
link. A public CA cannot issue a certificate for a private IP address. Serving
the terminal from LuCI's own origin would remove that step but requires a
reverse proxy (nginx), which uhttpd does not provide.

## Manual configuration

Without the updated package, the same result is reached with:

```sh
uci set ttyd.@ttyd[0].ssl=1
uci set ttyd.@ttyd[0].ssl_cert=/etc/ssl/acme/router6.example.invalid.fullchain.crt
uci set ttyd.@ttyd[0].ssl_key=/etc/ssl/acme/router6.example.invalid.key
uci commit ttyd && /etc/init.d/ttyd restart
```

The stock init script does not restart ttyd after certificate renewal; run
`/etc/init.d/ttyd restart` after a renewal. Recover the previous state with
`uci set ttyd.@ttyd[0].ssl=0; uci commit ttyd; /etc/init.d/ttyd restart`.

## Sources

Feed commits are mirrored as `patches/feeds/0027-packages-ttyd-https.patch`
and `patches/feeds/0028-luci-ttyd-https.patch`, with baselines in
`configs/ttyd-https-feeds.json`. See the
[validation record](ttyd-https-validation.md).
