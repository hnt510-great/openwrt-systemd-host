# Moving dae's proxy plane into the kernel: design study

Written 2026-11-04 for the `daed` package (`package/custom/daed`, dae core
v2.1.1, outbound library `olicesx/outbound`
`v0.0.0-sticky-ip.0.20260918090140-cc86ced2e683`) on the Linux 7.3 x86-64
image. The question was whether dae's userspace proxy plane can be moved into
a kernel module (`.ko`), and whether that would make proxying faster on this
router: a Celeron N5105 (Tremont cores with AES-NI and PCLMULQDQ, no AVX2)
behind a 2.5 Gbps WAN, using VLESS with XTLS Vision over REALITY/TLS.

This is a design study only. Nothing was built, benchmarked or installed, and
the router was not touched. Every throughput or CPU figure below is either an
order-of-magnitude **estimate** (marked as such) or a published figure with its
source. Source references point to the upstream trees: dae core paths start
with `control/` or `common/`, outbound paths with `protocol/` or `netproxy/`,
kernel paths with `net/`.

## Answer

- **The whole proxy plane cannot reasonably move into a `.ko`.** The
  REALITY/uTLS handshake, Vision's padding phase, DNS, sniffing, routing,
  dialer groups, health checks and QUIC must stay in userspace. Only the
  per-byte part can move: relaying bytes between two sockets and, at most,
  encrypting TLS 1.3 records with keys negotiated in userspace.
- **A kernel module would not make the encryption cheaper.** Go and the kernel
  use the same AES-NI/PCLMULQDQ instructions, so AES-GCM costs about the same
  per byte in either place. What a module can remove is memory copies between
  kernel and userspace, syscalls, and Go scheduler wakeups.
- **For Vision traffic most bytes already carry no outer encryption, but dae
  still copies them through userspace.** When the traffic inside the tunnel is
  TLS 1.3, Vision switches both directions to the raw TCP socket after the
  first few records. dae's relay cannot see through Vision's connection type,
  so it neither splices nor uses its own in-kernel relay for these flows. It
  copies every byte twice through a 32 KiB Go buffer.
- **Recommendation:** do not write a kernel module. The improvement that is
  actually available for this traffic is a userspace handover of Vision's raw
  sockets to `splice(2)` (option A below). It removes both copies without new
  kernel code. A custom module (option C) would only be worth building if
  measurements later show that syscalls and wakeups, not copies, limit a
  single flow on the N5105.
- **Expected effect (estimate):** less CPU per proxied byte. At 2.5 Gbps a
  visible change in throughput or latency is only expected if a single flow is
  currently limited by one saturated core. Whether it is was not measured; the
  [measurement protocol](#measurement-protocol-not-run) describes how to find
  out.

## Current data path

```
LAN client
  -> br-lan, tcx eBPF (tproxy.c)       direct flows: routed by the kernel, done
  -> netkit dae0 -> daens namespace    proxied flows only
  -> Go tproxy listener (daed)
       sniff (SNI/HTTP/QUIC), route, pick a dialer from the group
       dial: TCP -> uTLS REALITY handshake -> VLESS header -> Vision
       relay: relayCore, one goroutine per direction
  -> outbound TCP socket -> WAN -> proxy server
```

Direct traffic never leaves the kernel. For proxied TCP the relay is
`relayCore` (`control/tcp_relay_core.go`), which calls
`defaultRelayCopyEngine.Copy` (`control/tcp_copy_engine.go:49`) per
direction. Copy picks one of three paths:

| Path | When | Per-byte work |
| --- | --- | --- |
| eBPF sockmap relay, `tryOffloadTCPRelay` (`control/tcp_offload_linux.go:136`) | Both sides unwrap to `*net.TCPConn` **and** `DAE_ALLOW_TCP_SOCKMAP=1` | Kernel only: `sk_skb/tcp_offload_redirect` (`control/kern/tproxy.c:4264`) redirects each received skb to the peer socket through the `fast_sock` SOCKHASH |
| Splice fast path, `relayFastCopy` (`control/tcp_copy_linux.go:38`) | Both sides unwrap to `*net.TCPConn` (`shouldUseRelayFastPath`, `control/tcp_copy_linux.go:339`) | `splice(2)` through a pipe: no userspace copy, two syscalls per chunk |
| Copy loop, `relayCopyLoop` (`control/tcp_copy_engine.go:68`) | Anything else | `Read` into a 32 KiB buffer (`relayCopyBufferSize`, `control/tcp_copy_engine.go:23`), then `Write`: two copies plus at least two syscalls per chunk |

"Unwraps to `*net.TCPConn`" is decided by `unwrapRelayTCPConn`
(`control/tcp_relay_capabilities.go:61`) and `netproxy.UnwrapTCPConn`
(`netproxy/unwrap.go`). In practice the first two paths cover direct flows that
went through userspace for sniffing, plus SOCKS5 and HTTP proxies. Every
encrypted outbound takes the copy loop.

### The sockmap relay is opt-in and has a history

The in-kernel relay is off unless `DAE_ALLOW_TCP_SOCKMAP=1` is set
(`control/control_plane_core_bind.go:366`). The code gives two reasons:
CVE-2025-38165 (a sockmap panic on large redirected messages, fixed in 6.15.3
and the stable backports listed in `common/consts/ebpf.go:115`, so Linux 7.3 is
not affected), and the psock ingress queue that is not charged to socket buffers
or memcg, so a slow reader can grow kernel memory without bound. dae limits
this with a 64 MiB per-session backlog "fuse" that falls back to userspace
(`tcpOffloadMaxPeerBacklog`, `control/tcp_offload_linux.go`). Upstream dae
removed an earlier sockmap fast path in
[dae#912](https://github.com/daeuniverse/dae/pull/912), calling sockmap one of
the buggiest kernel features.

### What Vision does after the inner handshake

Vision is a client-side wrapper (`protocol/vless/vision/`, derived from
mihomo). For the first few records it pads and filters the inner traffic
through the outer TLS connection. If the inner traffic is TLS 1.3 with a
supported cipher suite (`filter.go:117`, which sets `enableXTLS`), the client
sends `commandPaddingDirect`:

- **Upload:** after that command `writeWrapper.writeDirect` is set
  (`conn.go:407`, `conn.go:434`) and writes go to the raw TCP socket
  (`conn.go:42`), not through the outer TLS connection.
- **Download:** once the server's direct command arrives and the outer TLS
  connection's buffered plaintext and raw bytes are drained, `directRead` is set
  (`conn.go:283`) and reads come from the raw TCP socket (`conn.go:29`).

After both switches the connection is a plain TCP-to-TCP relay: the inner TLS
1.3 records pass through unchanged and the outer TLS layer does no work. If the
inner traffic is not TLS 1.3 (plain HTTP, TLS 1.2, UDP), the flow stays inside
the outer TLS connection for its whole life.

`vision.Conn` (`protocol/vless/vision/conn.go`) embeds the raw `net.Conn` but
does not implement `UnderlyingConnProvider`, so `unwrapRelayTCPConn` returns
false for it. dae therefore always relays Vision through `relayCopyLoop`, even
after the switch. Vision's own splice-based `WriteTo` (`conn.go:156`) is never
called by dae's copy loop, and its `ReadFrom` is commented out (`conn.go:312`).
That is the main inefficiency for this router's traffic, and it is a userspace
issue.

## What can and cannot move into a kernel module

| Component | Runs | In a `.ko`? | Reason |
| --- | --- | --- | --- |
| Interception, direct routing | per packet | Already kernel (tcx eBPF) | — |
| tproxy accept, sniffing (SNI, HTTP Host, QUIC) | per flow | No | Parses untrusted application data; already decided early, cheap per byte |
| Routing rules (domain, process, GeoIP/GeoSite) | per flow | No | IP rules are in eBPF already; domain rules need the sniffed name and DNS state |
| DNS controller, cache, upstream groups | per query | No | Complex stateful protocol handling; no per-byte cost |
| Dialer groups, health checks, subscriptions | control | No | Control-plane logic, network fetches, configuration |
| uTLS/REALITY handshake | per flow | No | X25519, certificate checks, REALITY authentication, fingerprinted ClientHello; the kernel itself passes TLS handshakes to the userspace `tlshd` daemon (`net/handshake`) |
| Vision padding phase | first records | No | Short, stateful, protocol-specific |
| Relay after Vision's switch | per byte | Yes | Plain TCP-to-TCP: splice, sockmap or a module |
| Outer TLS 1.3 record encryption (not switched) | per byte | In principle | Like kTLS, after userspace hands over keys; see option D |
| UDP over Vision (VLESS UDP framing inside outer TLS) | per packet | Not reasonably | Framing plus TLS records plus per-packet routing state |
| QUIC outbounds (Hysteria2, TUIC, Juicity) | per packet | No | In-kernel QUIC is not merged ([LWN](https://lwn.net/Articles/1029851/); v11 posted 2026-03-24) and keeps the handshake in userspace |

A module holding "all" of the proxy plane would put a TLS/REALITY stack, a DNS
resolver and a rule engine in ring 0. A bug there is a kernel oops on the
router instead of a `daed` restart.

## Kernel mechanisms on Linux 7.3

- **`splice(2)` between two TCP sockets.** Data moves through a pipe without
  being copied into userspace. A userspace thread still issues two syscalls per
  chunk (Go's `TCPConn.ReadFrom` moves up to 1 MiB per call). Backpressure is
  ordinary TCP flow control. Mature and safe; dae already uses it for raw pairs.
- **sockmap `sk_skb` stream-verdict redirect.** No syscalls per chunk: received
  skbs are queued to the peer psock and sent from a kernel workqueue. Caveats:
  the uncharged ingress queue described above, a long bug history, and that
  sockets with any ULP (such as kTLS) cannot be added (`sk_psock_init`,
  `net/core/skmsg.c:757`).
- **kTLS (`CONFIG_TLS`).** Not enabled in this kernel; enabling it means
  selecting `kmod-tls`, which changes the kernel configuration and needs a new
  kernel generation. In 7.3 kTLS and sockmap exclude each other in both
  directions: `do_tls_setsockopt_conf` returns `-EINVAL` on a socket that
  already has a psock (`net/tls/tls_main.c:636`, in the unmodified 7.3.1
  source), and sockmap rejects TLS sockets as noted above. kTLS can therefore
  only be combined with `splice(2)` driven from userspace. sing-box ships kTLS
  and documents that TX "may only improve performance when `splice(2)` is
  available" and that RX "will definitely degrade performance even if
  `splice(2)` is in use"
  ([sing-box TLS options](https://sing-box.sagernet.org/configuration/shared/tls/)).
  It also needs the traffic keys and record sequence numbers, which Go's
  `crypto/tls` and uTLS do not export (sing-box reads them through reflection).
- **In-kernel QUIC.** Unmerged; not usable for Hysteria2/TUIC/Juicity.
- **A custom module.** Possible: it can use the kernel AEAD API (`gcm(aes)` maps
  to the AES-NI driver), `read_sock`/`tcp_read_skb`, and
  `sendmsg(MSG_SPLICE_PAGES)`. Its constraints:
  - It must be GPL-compatible to use the networking and crypto symbols. dae and
    the outbound library are AGPL-3.0, so the module has to be written from the
    protocol specifications, not translated from their code.
  - It is out of tree and must be ported for each mainline series that
    `scripts/update-mainline-kernel.py` moves to.
  - In this tree a new kmod is packaged into `linux-image-<kver>-N-openwrt` and
    needs a reserved kernel generation and a trial reboot
    ([kernel upgrades](kernel-upgrade.md)).
  - No in-kernel Shadowsocks, VLESS or Trojan implementation was found to build
    on.

Being in the kernel is not automatically faster. Tailscale's userspace
wireguard-go overtook in-kernel WireGuard on the same hardware (13.0 versus
11.8 Gb/s) once it batched packets with UDP GSO/GRO
([Surpassing 10Gb/s over Tailscale](https://tailscale.com/blog/more-throughput),
2023). Batching and avoiding copies matter more than which side of the syscall
boundary the code runs on.

## Design options for Vision, ranked by risk

### A: hand Vision's raw sockets to splice (recommended)

**Status:** implemented in `daed` 2.1.1-r4 as patches
`006-outbound-vision-offer-raw-sockets-after-direct-switch.patch` and
`007-dae-core-splice-vision-direct-flows.patch`; host-side checks are in the
[validation record](daed-validation.md#vision-splice-handover-daed-211-r4).
Run E4 below has not been measured on the router. The work also found that
over `security=tls` (not REALITY) Vision's direct-mode writes were buffered in
the TLS record coalescer until the next read; patch 006 flushes them.

When a direction has switched to direct mode, that direction is a raw socket
on both ends. The change:

1. Vision exposes, per direction, the raw `*net.TCPConn` once it is safe:
   for reads after `directRead` is set (the outer TLS connection's buffered
   bytes are already drained at that point, `conn.go:245-284`); for writes after
   `writeDirect` is set, once any coalesced outer writes have been flushed so
   that byte order is kept.
2. `relayCopyLoop` checks after each chunk whether its source and destination
   now both resolve to raw TCP and, if so, continues that direction with
   `relayFastCopy` (splice) and the same traffic accounting.
3. Half-close (`CloseWrite`) must reach the raw socket after the switch.

Files: `protocol/vless/vision/conn.go` in the outbound library
(`third_party/outbound` in the recipe), and `control/tcp_copy_engine.go`,
`control/tcp_relay_capabilities.go` in dae core. Both are already patched
locally through `package/custom/daed/patches/`.

Effect: removes both userspace copies for switched flows; keeps the
syscalls and the Go goroutines. No kernel change, no new kernel generation, no
new failure mode in the kernel.

### B: hand switched pairs to the existing sockmap relay

Once *both* directions have switched, register the pair with dae's existing
offload (`tryOffloadTCPRelay`), reusing `tcpOffloadFlushLeftPrefix` and
`tcpConnDrainKernelQueue` for bytes already queued. This removes the syscalls
and wakeups as well. Today the offload is decided once before the relay starts
(`control/tcp.go:309`); a handover in the middle of a relay needs both copy
goroutines stopped at a safe point first. It stays behind
`DAE_ALLOW_TCP_SOCKMAP=1` and inherits the uncharged-memory risk.

### C: a custom raw relay module (`kmod-dae-kproxy`)

A replacement for sockmap with real flow control, used for the same switched
pairs as B:

- Control: dae passes the two socket file descriptors to a `/dev/dae-kproxy`
  ioctl after the switch; it gets a handle back and polls it for completion
  and byte counters, so accounting and connection logs stay in dae.
- Receive: `sk_data_ready` schedules a work item that drains the receive queue
  with `read_sock`/`tcp_read_skb`.
- Send: `sendmsg(MSG_SPLICE_PAGES)` on the peer, without copying payload pages.
- Flow control: stop reading when the peer's free send-buffer space
  (`sk_stream_wspace`) runs low and resume from `sk_write_space`, so TCP
  backpressure reaches the sender instead of an unbounded queue.
- Shutdown: forward FIN as a half-close and RST as an abort; release both
  sockets and signal the handle.

This is only justified if B is clearly faster than A in measurements and the
sockmap memory issue is a real concern. It carries all the module constraints
listed above.

### D: C plus a TLS 1.3 record transform (not recommended)

To cover flows that never switch (inner plain HTTP or TLS 1.2, and the outer
TLS of other protocols such as Trojan or VLESS without Vision), the module
would also encrypt and decrypt TLS 1.3 records:

- dae would have to derive the traffic keys from uTLS (key-log secrets
  expanded with HKDF-Expand-Label) and read the current record sequence
  numbers through reflection, as sing-box does.
- Records other than application data (NewSessionTicket, KeyUpdate, alerts)
  would have to be handed back to userspace.
- Encryption would use the kernel AEAD API at the same speed as Go.

The saving is the same copies and syscalls as C, for a minority of Vision's
bytes, at the cost of a TLS record layer in ring 0. kTLS cannot be reused for
this because it cannot be combined with an in-kernel relay on 7.3.

## Cost model at 2.5 Gbps on the N5105 (estimates)

2.5 Gbps is about 312 MB/s. For a switched Vision flow at that rate:

| Cost | Today (copy loop) | A (splice) | B or C (in-kernel relay) |
| --- | --- | --- | --- |
| Kernel TCP receive and send, netkit/eBPF, NIC driver, GRO/TSO | yes | yes | yes |
| Outer TLS encryption | no (switched) | no | no |
| Copies between kernel and userspace | ~625 MB/s | none | none |
| Syscalls | at least ~19,000/s (32 KiB reads and writes) | similar or fewer (splice calls of up to 1 MiB) | none per chunk |
| Go netpoll and goroutine wakeups | per chunk | per chunk | none |

**Estimate:** assuming a Tremont core copies 5 to 10 GB/s, 625 MB/s of copying
is roughly 6 to 12 % of one core. Syscalls and wakeups at these rates are
likely a few percent more. The kernel networking work in the first row, which
no option removes, is probably the largest part. Option A should therefore
save a measurable share of one of the four cores at line rate, and B or C only
somewhat more. None of these figures were measured.

Other traffic:

- **Not switched (inner plain HTTP or TLS 1.2):** adds AES-GCM through the outer
  TLS connection. That costs the same in Go and in a kernel module; only option
  D would remove the copies around it.
- **UDP through Vision, mainly QUIC/HTTP/3:** stays inside the outer TLS
  connection and is handled per packet in userspace. It is likely the most
  expensive path per byte, and no option here moves it. If it dominates, a
  routing rule that blocks proxied UDP 443 makes browsers fall back to TCP,
  where Vision can switch. The cost is a fallback delay on first contact.
- **Latency:** userspace adds microseconds per wakeup; that is negligible
  against WAN round trips.

## Measurement protocol (not run)

These measurements would decide between A, B and C. They reuse the topology
of `scripts/tests/test-daed-vm.py` (router and client VMs booting the exact
image), with these changes:

- The image's `xray-core` acts as a local VLESS + REALITY + Vision server on
  the WAN side.
- The client downloads and uploads large files over HTTPS (TLS 1.3) from a
  server on the WAN side, because Vision only switches on inner TLS 1.3. Plain
  `iperf3` through the same node measures the path that never switches.
- The VM link uses tap or vhost-net instead of QEMU's socket netdev, which would
  otherwise be the bottleneck.

| Run | Path |
| --- | --- |
| E0 | Routed direct (no dae), baseline |
| E1 | SOCKS5 node through dae's default relay (splice) |
| E2 | E1 with `DAE_ALLOW_TCP_SOCKMAP=1` (sockmap relay) |
| E3 | Vision as today (copy loop after the switch) |
| E4 | Vision with option A |

Record throughput and CPU cycles per byte for the router (with `perf stat -a`,
or `daed` process time plus softirq time from `/proc/stat`). A `perf record`
call graph splits the cost into crypto, copies, syscalls, the Go runtime and
the kernel TCP stack. Calibrate against the N5105 with
`openssl speed -evp aes-128-gcm` on both CPUs. Build option C only if E2 clearly
beats E1 and E4 still shows a single flow limited by CPU below the line rate.

## Sources

- dae v2.1.1 core, dae-wing `b089b56` and the outbound library version
  pinned in `package/custom/daed/Makefile`; Linux 7.3.1
  (`dl/linux-7.3.1.tar.xz`).
- [dae#912: fix: Remove sockmap fast tcp redirect](https://github.com/daeuniverse/dae/pull/912)
- [sing-box TLS options, `kernel_tx`/`kernel_rx`](https://sing-box.sagernet.org/configuration/shared/tls/)
- [LWN: QUIC in the kernel](https://lwn.net/Articles/1029851/) and the
  [v11 series](https://yhbt.net/lore/linux-cifs/cover.1774410440.git.lucien.xin@gmail.com/)
- [Tailscale: Surpassing 10Gb/s over Tailscale](https://tailscale.com/blog/more-throughput)
- [netdev: tls: reject attaching TLS to sockets already in sockmap](https://lore.kernel.ime.usp.br/netdev/20260321074155.6fdb79dc@kernel.org/t/)

See also [daed](daed.md).
