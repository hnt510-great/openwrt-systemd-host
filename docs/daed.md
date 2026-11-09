# daed (dae with a web dashboard)

[dae](https://github.com/daeuniverse/dae) is a transparent proxy that splits
traffic inside the kernel. eBPF programs on the LAN (and optionally WAN) tc
hooks decide per packet whether a flow goes direct or to a proxy node. Direct
traffic is forwarded by the kernel like any routed packet and never passes
through a proxy process. Only proxied flows are redirected into dae's private
`daens` network namespace and relayed by the daemon.

[daed](https://github.com/daeuniverse/daed) is dae plus its GraphQL backend
(dae-wing) and a web dashboard in one binary. The x86-64 native-systemd image
ships `daed` **disabled** as an opt-in alternative to Passwall. Passwall stays
installed and remains the default.

## What is in the image

| Package | Contents |
| --- | --- |
| `daed` | `/usr/bin/daed` (static Go binary with the embedded dashboard and BPF objects), `/etc/init.d/daed`, `/etc/config/daed` |
| `daed-geoip`, `daed-geosite` | `/usr/share/dae/{geoip,geosite}.dat`, symlinks to the `v2ray-geoip`/`v2ray-geosite` data that Passwall also uses |
| `kmod-sched-bpf` | `cls_bpf`/`act_bpf` for the tc BPF classifier |

The recipe is `package/custom/daed`; the config fragment is
`configs/daed.config`.

### Upstream version and backports

The daed **v2.1.1** release bundles a dae core from 2026-04-22 (`85a1fc3`,
before dae v2.0.0rc1). Most fixes released in dae v2.1.1 live in or after the
2026 "kdae" datapath and control-plane rework (`1ec85fe`), so they cannot be
lifted onto that core individually: applying every fix from `85a1fc3` up to
v2.1.1 produces the v2.1.1 core itself. This package therefore re-pins the
core instead, the same way upstream dae-wing did after the daed release:

| Component | Source |
| --- | --- |
| Backend | dae-wing `b089b56` ("bump dae-core to v2.1.1 and follow its control plane API"), the dae-wing main branch after daed v2.1.1 |
| dae core | dae **v2.1.1** release `dae-full-src.tar.xz` (identical to the `v2.1.1` tag plus the BPF headers submodule) |
| Dashboard | daed v2.1.1 `web.zip`, unchanged |
| Outbound library | The `github.com/olicesx/outbound` module version that dae-wing and the core already pin (`replace github.com/daeuniverse/outbound => …`), as the Go proxy zip that `go.sum` verifies, unpacked to `third_party/outbound` so it can be patched |

On top of the v2.1.1 core, `package/custom/daed/patches/` carries three
later upstream dae fixes (code only; docs and changelog hunks dropped) and
four local changes:

| Patch | Upstream | Fix |
| --- | --- | --- |
| `001-dae-core-restore-Marshaller-Bytes.patch` | `6f2f2aa` | Restores `config.Marshaller.Bytes`, which dae-wing `b089b56` calls; without it the backend does not compile against v2.1.1 |
| `002-dae-core-exact-match-for-LAN-UDP-local-services.patch` | `fb5eae6` | LAN UDP is bypassed to a local service (such as dnsmasq on port 53) only on an exact address match |
| `003-dae-core-stop-LAN-ICMP-redirects.patch` | `e3fee8f` | Also writes `conf/all/send_redirects=0`; the kernel ORs it with the per-interface value, so the router otherwise kept sending ICMP redirects that steer LAN hosts past dae |
| `004-dae-wing-default-lan-interface-for-new-configs.patch` | local | A config created with an empty `lan_interface` gets the UCI `default_lan_interface` (`br-lan`); see [No LAN interface](#no-lan-interface-lan-traffic-goes-direct) |
| `005-outbound-vision-udp-read-with-64k-buffer.patch` | local | Vision UDP replies are read into dae's 64 KiB DNS buffer instead of failing with `short buffer`; points both `go.mod` replace directives at `third_party/outbound`; see [DNS warnings](#dns-warnings-through-a-vision-node) |
| `006-outbound-vision-offer-raw-sockets-after-direct-switch.patch` | local | Vision offers its raw socket per direction once that direction has switched to direct mode (`netproxy.DirectTCPConnProvider`); direct-mode writes over plain TLS are flushed instead of waiting in the record coalescer; see [Vision flows after the direct switch](#vision-flows-after-the-direct-switch) |
| `007-dae-core-splice-vision-direct-flows.patch` | local | dae's copy loop moves a switched Vision direction to its `splice(2)` loop |

Release **2.1.1-r8** keeps the local DNS/connection audit patches (008–009)
and adds five later upstream dae fixes, refreshed with the package quilt workflow:

| Patch | Upstream | Fix |
| --- | --- | --- |
| `010-dae-core-flush-short-splice-writes.patch` | [`17cc1de`](https://github.com/daeuniverse/dae/commit/17cc1de85dd0ae82f69cf0c182d99a1c35b193eb) | Removes `SPLICE_F_MORE` so short TCP replies do not wait for the cork timer, including after Vision hands over to splice |
| `011-dae-core-recover-locked-netns.patch` | [`2649d5b`](https://github.com/daeuniverse/dae/commit/2649d5b3e853249ccb45527066a0d7cbffff465d) | Reports stale named-netns cleanup errors and recovers the specific kernel-locked mount signature |
| `012-dae-core-validate-fixed-domain-ttl.patch` | [`5a5473d`](https://github.com/daeuniverse/dae/commit/5a5473d5123983588f6d0befbb41ae3f7a744234) | Corrects digit-prefixed config hints and checks fixed-domain TTLs in dae's CLI validator; daed does not expose that CLI subcommand |
| `013-dae-core-bootstrap-resolver-address-family.patch` | [`e6e52bb`](https://github.com/daeuniverse/dae/commit/e6e52bbc3c75211f318c59f5890f6ba13e7effde) | Dials bootstrap DNS using the resolver address family rather than the requesting flow's family |
| `014-dae-core-strict-alignment-L3-loads.patch` | [`8722db0`](https://github.com/daeuniverse/dae/commit/8722db01fca702818ea85cefde46a84dd755f44a) | Uses safe packet loads for L3 hooks on strict-alignment kernels; includes the upstream production BPF verifier test file in full because it was added after v2.1.1 |

The namespace recovery in patch 011 only covers `/run/netns` with a fresh
mode-0755 tmpfs if both synchronous and lazy unmount fail with `EINVAL` and
removing the stale entry fails with `EBUSY`. Other cleanup failures stop startup
with their cause. A recovery cover hides other tools' named-netns entries in
that directory, logs their names, and persists until reboot; the underlying
namespaces are not destroyed. It does not mount a cover during normal startup.

As checked on 2026-11-09, daed and dae-wing were archived upstream on
2026-09-24. The recipe already pins the final dae-wing main commit `b089b56`
and the latest daed dashboard release v2.1.1. Maintaining the composed recipe
and selectively backporting dae fixes remains necessary while those projects
stay archived.

The dashboard of daed v2.1.1 is compatible with the re-pinned backend: the
GraphQL schemas differ only in the global config, where `soMarkFromDaeSet` was
removed and `disableThp`, `autoSniffPunt` and `bpfConnStateMapSize` were
added; the dashboard never uses `soMarkFromDaeSet`, and every field it queries
still exists. The new options keep their defaults because the dashboard does
not show them.

`daed --version` reports `2.1.1` (the dashboard release). Because the recipe
is composed from four sources, `configs/custom-package-updates.json`
registers it as `local`, so `./scripts/feeds update` does not bump it. When a
daed release bundles dae core 2.1.1 or newer, switch the recipe back to that
release's `daed-full-src.zip` and register it as a GitHub release with
`"companion_assets": {"DAED_WEB_HASH": "web.zip"}` so the updater also
refreshes the dashboard hash; drop patches that the new core contains.

## Kernel requirements

dae loads CO-RE BPF programs and needs these kernel options. The image
enables them through `configs/daed.config`:

| Option | Why |
| --- | --- |
| `CONFIG_KERNEL_DEBUG_INFO_BTF=y` (with `# CONFIG_KERNEL_DEBUG_INFO_REDUCED is not set`) | `/sys/kernel/btf/vmlinux` for BPF CO-RE relocations |
| `CONFIG_KERNEL_MODULE_ALLOW_BTF_MISMATCH=y` | Out-of-tree modules built on the device against `kernel-dev-headers` (no `vmlinux`) still load |
| `CONFIG_KERNEL_BPF_STREAM_PARSER=y` | `SOCKMAP`/`SOCKHASH` for the in-kernel TCP relay (new knob in `config/Config-kernel.in`) |
| `CONFIG_KERNEL_NETKIT=y` | netkit link into `daens`; dae falls back to veth without it (new knob) |
| `kmod-sched-bpf`, `kmod-sched-core` | `cls_bpf` classifier and the `clsact` qdisc |

BPF syscall/JIT, cgroup BPF, kprobes and BPF trace events were already on.
The `daed` package depends on the BTF and stream-parser knobs, so it cannot
be selected without them.

These options change the kernel ABI hash, so installing daed through APK on a
router that runs an older generation needs the new **kernel generation** and
a trial reboot first:

1. Publish with `scripts/build-and-publish.sh` (or `build-and-publish.py`),
   which reserves the generation.
2. On the router: `apk upgrade`; APK installs the new kernel and complete
   kmod set as a new generation and arms a trial boot.
3. Reboot and confirm with `kernelctl check` (see
   [kernel upgrades](kernel-upgrade.md)).

BTF costs build time and size: the kernel is built with full DWARF and
`pahole` (`tools/dwarves`) converts it to BTF; `vmlinux` carries the `.BTF`
section and kmods carry split BTF. The eBPF objects are compiled with the
LLVM BPF toolchain from `tools/llvm-bpf` (`CONFIG_BPF_TOOLCHAIN_BUILD_LLVM`),
built once per build tree.

## Enable

daed and Passwall both intercept forwarded traffic (tc eBPF versus nftables
TPROXY) and must not run together. The init script refuses to start daed
while `passwall.@global[0].enabled` is `1` and logs:

```
daed: Passwall is enabled; disable it (uci set passwall.@global[0].enabled=0) before starting daed
```

It also watches the `passwall` config: enabling Passwall later and running
`reload_config` (or saving it in LuCI) stops daed.

```sh
uci set passwall.@global[0].enabled=0
uci commit passwall
/etc/init.d/passwall stop

uci set daed.config.enabled=1
uci commit daed
/etc/init.d/daed start
```

Then open `http://<router-lan-ip>:2023/` from the LAN and **create the admin
account immediately**: daed lets the first visitor create it. The listener is
`0.0.0.0:2023`; the `wan` zone's input policy rejects it from the internet,
while `lan` and `wireguard` (both `input ACCEPT`) can reach it.

In the dashboard:

1. **Global**: check that *LAN interface* is `br-lan` (new configs get it
   from `default_lan_interface`). *WAN interface* defaults to `auto`, which
   also proxies the router's own traffic; clear it if only LAN clients should
   be proxied. Keep *auto config kernel parameter* on. Also add every other
   interface whose clients should be proxied, such as the WireGuard server
   interface (`WIREGUARD` on this router): traffic forwarded from an
   interface that is not in *LAN interface* goes direct, because the WAN
   hook only proxies the router's own traffic. dae hooks layer-3 devices
   (WireGuard, tun, PPP) with its L3 programs.
2. **Nodes / Subscriptions**: import proxy links or a subscription.
3. **Groups**: create a group (for example `proxy`) and add nodes.
4. **Routing** and **DNS**: see below. Then select the config, routing and
   DNS and press *Run*.

The selection is stored in `/etc/daed/wing.db` (a conffile, kept by
sysupgrade and APK upgrades); after a restart daed resumes the last running
configuration.

### LuCI

`luci-app-daed` (in the image, with a Simplified Chinese translation) adds
**Services → daed**:

- **Enable** writes `daed.config.enabled`; *Save & Apply* starts or stops
  daed through its procd reload trigger. Dashboard address, *Default LAN
  interface* (a device picker; several devices allowed) and log rotation map
  to the UCI options below.
- **Status** shows whether procd runs daed and, when daed is enabled but
  stopped because Passwall is enabled, says so.
- **Dashboard** always shows an *Open dashboard* link and the URL,
  `http://<host>:<port>/`, using the host the browser used for LuCI when daed
  listens on all addresses. While daed is stopped the link stays visible and
  is marked *(daed is not running)*; with a loopback-only listen address the
  page says the dashboard is not reachable from the browser.
- **Restart** runs `/etc/init.d/daed restart`; **Log** shows the last 200
  lines of `/var/log/daed/daed.log`.

Nodes, groups, routing and DNS are not on this page; they live in the
daed dashboard. The ACL `luci-app-daed` grants the `daed` config (and read
access to `passwall` for the status), the procd service list, read access to
the network devices, interface dump, protocol handlers and `network` config
that the device picker loads, and exactly two commands:
`/usr/bin/tail -n 200 /var/log/daed/daed.log` and
`/etc/init.d/daed restart`. A restricted LuCI login needs `luci-base` plus
`luci-app-daed`.

### UCI options (`config daed 'config'`)

| Option | Default | Meaning |
| --- | --- | --- |
| `enabled` | `0` | Start daed at boot and on `start` |
| `listen_addr` | `0.0.0.0:2023` | Dashboard and GraphQL listener |
| `log_maxbackups` | `1` | Rotated log files kept under `/var/log/daed/` |
| `log_maxsize` | `5` | Log rotation size in MB |
| `default_lan_interface` | `br-lan` | LAN interfaces (a list, or a space-separated option) given to configs that daed creates from now on with an empty LAN interface, such as the dashboard's first-run config. Existing configs are not changed. Unset or empty means `br-lan`; to run a config without a LAN hook, clear *LAN interface* in the dashboard instead. Changing it restarts daed |

## Routing and DNS on this router

A minimal routing that keeps LAN and mainland China traffic direct:

```
pname(dnsmasq) && l4proto(udp) && dport(53) -> must_direct
dip(geoip:private) -> direct
dip(geoip:cn) -> direct
domain(geosite:cn) -> direct
fallback: proxy
```

dae intercepts DNS from LAN clients, including queries sent to dnsmasq on the
router, so it can learn which domain each flow belongs to. Keep dnsmasq as the
LAN resolver (local `*.lan` names, DHCP host names, the existing
`address=`/nftset entries) by sending DNS back to it:

```
upstream {
  dnsmasq: 'udp://127.0.0.1:53'
}
routing {
  request {
    fallback: dnsmasq
  }
  response {
    fallback: accept
  }
}
```

`fallback: asis` (send each query to the address the client asked) also
works when clients use the router as their resolver. The `must_direct` rule
above is only needed if the WAN device is bound, so that dnsmasq's own
upstream queries are not intercepted again.

The nftsets that dnsmasq fills for Passwall (`docs/dnsmasq-nftset.md`) are not
used by dae; dae's `domain()` rules replace them.

## Interaction with other router features

- **Flow offloading** (`flow_offloading '1'`): dae's LAN ingress hook runs
  before the netfilter flowtable, so it sees every packet. Proxied flows are
  redirected before netfilter and are never offloaded; direct flows are
  routed normally and can be offloaded. Validated with software offloading
  on; see the [validation record](daed-validation.md).
- **Full cone NAT** (`docs/fullcone-nat.md`): applies only to direct UDP that
  reaches the router's masquerade. Proxied UDP gets the proxy's NAT behaviour.
- **Firewall**: dae adds no fw4 rules. Hijacked packets enter `daens`
  through `dae0` and never traverse the host `input` chain; dae's own
  outbound connections and the replies it injects are covered by fw4's
  established/related rules.
- **systemd and procd**: daed is an rc service supervised by procd. In a
  native boot `openwrt-services.service` starts it; in the `procd recovery`
  boot procd does. Both mount bpffs at `/sys/fs/bpf` and cgroup2 at
  `/sys/fs/cgroup`.

### No LAN interface: LAN traffic goes direct

If the selected config has no `lan_interface`, dae binds only the WAN: the
router's own traffic is proxied while every forwarded LAN flow goes direct,
so the proxy looks half working. The log then has `Bind to WAN` but no
`Bind to LAN` line, and `/proc/net/nf_conntrack` shows LAN clients
masqueraded straight out of the WAN (proxied flows are redirected before
netfilter and leave no host conntrack entry).

Cause: the dashboard's first-run setup takes the LAN interface from the
interfaces that dae-wing flags as carrying a default route. dae-wing tests
`route.Dst == nil`, but netlink v1.3.1 reports default routes as `0.0.0.0/0`
and `::/0`, so nothing is flagged and the config is created with an empty
list; on a router the default-route interface would be the WAN anyway.
Patch 004 fills `default_lan_interface` into configs created from release
`2.1.1-r2` on. A `wing.db` created by `2.1.1-r1` keeps its empty list after
the upgrade: set *LAN interface* to `br-lan` under **Global** in the
dashboard, save, and run the config again, then confirm
`grep 'Bind to LAN' /var/log/daed/daed.log`.

### DNS warnings through a Vision node

With a VLESS `xtls-rprx-vision` node, UDP to the node is XUDP framed by the
outbound library's `vision.PacketConn`. Before release `2.1.1-r3` its
`ReadFrom` compared the reply length with `uint16(len(p))`; dae's DNS
forwarder passes a 65536-byte buffer, which wraps to 0, so every UDP DNS
reply through the node was discarded. The log then shows

```
WARN DNS forward to upstream failed ... error=short buffer network=udp+4 outbound=proxy ...
INFO ALIVE --udp4(DNS)-> NOT ALIVE: group=proxy
INFO Group has no dialer alive group=proxy network=udp4(DNS)
```

A `tcp+udp://` upstream still answers through the TCP retry, one round trip
later; a `udp://` upstream fails. Patch 005 fixes the reader. On an older
release, use `tcp://` for upstreams reached through the proxy.

Other warnings in the same place come from the node's TCP path, not from
dae: `tls: first record does not look like a TLS handshake` (the node's port
answered with something other than TLS) and `unexpected EOF` on TCP DNS.
When both the UDP and TCP attempts fail, the client gets SERVFAIL
(`DNS ingress fast path failed`). Check the node and its server logs for
those; daed runs with `--disable-timestamp`, so its log has no times to
correlate with.

### Vision flows after the direct switch

When the traffic inside a VLESS `xtls-rprx-vision` tunnel is TLS 1.3, Vision
stops wrapping it after the first records and each direction becomes a plain
relay to the node's TCP socket. Up to release `2.1.1-r3` dae could not see
that socket and kept copying both directions through a 32 KiB userspace
buffer. From `2.1.1-r4` (patches 006 and 007) the relay checks between
chunks, and once a direction has switched it continues with the same
`splice(2)` loop it uses for unwrapped TCP pairs, so the bytes stay in the
kernel. Traffic counters, the idle and half-close timeouts and half-close
itself behave as before. Nothing is configured; there is no kernel change.

What is not covered: Vision traffic whose inner protocol is not TLS 1.3 (it
never switches), UDP and QUIC through Vision, and nodes using TLS
fragmentation or a chained dialer (the socket is not offered through
wrappers that are not known to be transparent). Those keep the copy loop.
The [kernel proxy design study](dae-kernel-proxy-study.md) describes why
this was chosen over a kernel module (option A there).

Patch 006 also fixes a stall on `security=tls` Vision nodes (REALITY was not
affected): direct-mode uploads were buffered in the TLS record coalescer
until the download direction read something or 128 KiB had accumulated.

## Recovery

- `/etc/init.d/daed stop` detaches the BPF programs, removes `dae0` and the
  `daens` namespace, and traffic is routed normally again.
- On Linux 7.3 dae attaches with **tcx** BPF links, not `cls_bpf` filters, so
  `tc filter show dev br-lan ingress` stays empty while dae is active. Check
  the daemon's links instead:
  `grep -l '^link_type:.*tcx' /proc/$(pidof daed)/fdinfo/*`, or install
  `bpftool` and run `bpftool net show dev br-lan`. The link into `daens` is a
  netkit pair (`ip -d link show dae0` shows `netkit`).
- If the router is unreachable from the LAN after enabling daed, use the
  serial or local console: `uci set daed.config.enabled=0; uci commit daed;
  /etc/init.d/daed stop`.
- Logs: `/var/log/daed/daed.log` (tmpfs) and the system journal
  (`journalctl -t daed` for init script messages).
- To start over, stop daed and remove `/etc/daed/wing.db`; the next visit to
  the dashboard creates a new admin account.

## Tests

- `python3 scripts/tests/test-custom-package-updates.py` covers the updater's
  `.zip` sources and `companion_assets` refresh used for daed releases.
- `node scripts/tests/test-luci-daed-view.js` covers the LuCI view: listen
  address parsing, dashboard URLs, status texts, the ACL commands and
  read-only users.
- `python3 scripts/tests/test-daed-vm.py --image <exact .img.gz> --work-dir <new dir>`
  boots the image as router plus LAN client under KVM and checks the kernel
  options, the Passwall interlock, that a config created without a LAN
  interface (as the dashboard does) gets `br-lan`, direct and proxied
  routing through a fake SOCKS5 node, DNS, flow offloading, the backported
  `send_redirects` fix and cleanup on stop, and drives the LuCI ACL as a
  restricted `luci-base` + `luci-app-daed` login (log, denied commands, the
  device picker's network calls and setting the default LAN interface,
  enable/disable through `uci apply`, restart); it then boots the same disks once into the `procd
  recovery` entry (GRUB `next_entry`, as for a kernel trial) and repeats the
  autostart, routing and cleanup checks.

See the [validation record](daed-validation.md). Whether dae's proxy plane
could move into a kernel module is analysed in the
[kernel proxy design study](dae-kernel-proxy-study.md).
