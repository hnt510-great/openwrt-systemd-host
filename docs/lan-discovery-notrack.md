# LAN discovery notrack rules

firewall4 `r3` adds two one-time UCI migrations, ported from coolsnowwolf/lede
(`005-notrack-lan-ssdp-discovery.patch`, `006-notrack-lan-wsd-discovery.patch`).
They stop the router from creating conntrack entries for LAN multicast
discovery, which never needs tracking or NAT:

| Section | Family | Destination | Port | Used by |
| --- | --- | --- | --- | --- |
| `upnp_ssdp_notrack` | IPv4 | `239.255.255.250` | UDP 1900 | UPnP SSDP (`miniupnpd`, media renderers) |
| `wsd_ipv4_notrack` | IPv4 | `239.255.255.250` | UDP 3702 | WS-Discovery (`wsdd2`, Samba, printers) |
| `wsd_ipv6_notrack` | IPv6 | `ff02::c` | UDP 3702 | WS-Discovery |

Each rule is `src='lan'`, `target='NOTRACK'`. fw4 renders them into a
`notrack_lan` chain jumped from `raw_prerouting` for the LAN devices. Untracked
packets then reach the normal `input_lan` chain, so the LAN zone's input
policy still decides whether the router accepts them; with the default LAN
`input ACCEPT`, `miniupnpd` and `wsdd2` keep answering. Unicast replies and the
follow-up HTTP/TCP sessions are ordinary tracked traffic.

## When the migrations run

The scripts are `/etc/uci-defaults/95-upnp-ssdp-notrack` and
`/etc/uci-defaults/96-wsd-notrack`. They run once, on first boot of a new
image or when APK installs or upgrades `firewall4`, and are then deleted. They:

- do nothing when the firewall has no zone named `lan`;
- leave an existing section with the same name untouched, including one with
  `enabled='0'`, so removing a rule permanently is done by disabling it rather
  than deleting it;
- commit only `firewall`; reload the firewall to apply on a running router.

## Check and disable

```sh
uci show firewall | grep -E 'ssdp_notrack|wsd_.*_notrack'
nft list chain inet fw4 notrack_lan
fw4 reload
```

To keep a rule off across upgrades:

```sh
uci set firewall.wsd_ipv6_notrack.enabled='0'
uci commit firewall
fw4 reload
```

See [the validation record](lan-discovery-notrack-validation.md).
