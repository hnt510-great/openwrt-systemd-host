# Plan: Router-first resource policy, and an adaptive governor only if it earns its place

Status: plan approved by the user on 2026-11-07. Implementation has not started: nothing is built,
and the router has not been changed (only read-only probes have run). Agents picking this up should
read [§12 Handoff notes](#12-handoff-notes-for-the-implementing-agent) first, then record each
gate outcome (G0, G1, G2) in this status line as it happens.

## Context

The N5105 router (4 cores, no SMT, 7.6 GiB RAM, Linux 7.3.3-55, native systemd, cgroup v2) is both
the production router and a GNOME, VM, container and build host. The goal is to keep routing
throughput, latency, loss and reliability within limits while general-purpose work uses all spare
capacity. Network IRQ steering was tuned and validated on 2026-10-31
(`/srv/openwrt-validation/steering-backup-20261031/bench.py`) and must stay exactly as it is.

The user asked for a plan only. Nothing here gets implemented, deployed or applied to the router
until the user approves each phase that touches it. All probes made for this plan were read-only.

**Recommendation.** Build this in stages, and let measurements decide each step:

1. Build a reproducible A/B harness and measure baseline (**B0**) degradation under contention.
   If B0 shows no material degradation, stop: no governor is justified.
2. Ship a **static, work-conserving** policy (**S**): systemd drop-ins only, no daemon. It covers
   memory protection, OOM ordering and CPU classes. Ship it only if it beats B0.
3. Build the **adaptive governor** (**A** = S + a small daemon) only if S leaves a measured residual
   that a non-work-conserving lever can recover, as shown in a manual lever sweep. Ship A only if it
   beats S.

There are three valid end states: ship nothing, ship S, or ship S plus A. Each is decided by
pre-registered criteria. **If A does not beat S by the declared margins, A is a failed project in
its current form, and the result is documented as such.**

---

## 1. Evidence gathered (repository and read-only router probe, 2026-11-07)

| Area | Finding | Implication |
|---|---|---|
| CPU | N5105, 4C/4T, intel_pstate powersave + EPP balance_performance, C3_ACPI exit latency **1048 µs** | Idle-path latency is *worse* than loaded latency (2026-10-31 data: gateway p95 0.5–0.6 ms idle vs 0.16–0.4 ms loaded). Record C-state and frequency as covariates. |
| Kernel | HZ=100, PREEMPT_LAZY, PSI=y, CFS_BANDWIDTH, CPUSETS, BLK_DEV_THROTTLING, **RT_GROUP_SCHED=y**; no IRQ_TIME_ACCOUNTING (no `/proc/pressure/irq`), no IOCOST/IOLATENCY, no sched_ext/UCLAMP | `io.weight` has no effect (NVMe uses `none`; BFQ is loaded but unused). Softirq time is tick-sampled. Lazy preemption with a 10 ms tick can delay fair-class wakeups (hypothesis H2). |
| cgroup | Controllers `cpuset cpu io memory pids` at root and system.slice; user.slice has `cpu memory pids`. Mount options: **`nsdelegate` only (no `memory_recursiveprot`)** | `MemoryLow` must be set explicitly on every ancestor. |
| Placement | procd instances → `openwrt.slice/openwrt-<svc>.slice/openwrt-<svc>@<inst>.service` (procd `130-systemd-transient-units.patch` sets Slice, Nice, OOMPolicy=continue, no OOMScoreAdjust); ubusd/procd/rc units, sshd, hermes, router-audit, cockpit, virtqemud → system.slice; GNOME → `user@32769.service/session.slice` (gnome-shell, pipewire), Sunshine/apps → `app.slice`; SSH logins and coding agents → `user-32769.slice/session-*.scope`; libvirt → machine.slice; ksoftirqd/kswapd/kworkers → root cgroup | No slice sets CPUWeight, IOWeight, MemoryLow or limits. The upstream user `background.slice` has CPUWeight=30. **systemd-oomd 262 is installed but disabled.** |
| Memory | 7.8 GiB zram swap (prio 100), swappiness 60, min_free_kbytes 67584; openwrt.slice 322 MiB (daed 145, passwall_server 50), system.slice 1.18 GiB, user.slice 2.0 GiB | Reclaim and zstd compression run in kswapd (root) or the allocating task. Router daemons are not protected from reclaim or from the kernel OOM killer. |
| Network | eth0 LAN and eth1 WAN are igc 2.5G with 4 TxRx queues; **irqbalance `-c 2 -t 10` moves IRQs every 10 s**; RPS mask `f` on all queues; netdev_budget_usecs 20000; netdev_max_backlog 8192; flow_offloading=1, fullcone=2; PPPoE + CAKE egress 130 Mbit; daed (TCX eBPF + Go userspace), passwall_server sing-box, haproxy | Do not touch any of this. eth2 and eth3 are unused igc ports. |
| Routing load | 2026-10-31 bench: WAN ≈130 Mbit up / 150–210 Mbit down through the proxy, per-CPU softirq ≤ 7%, busy ≤ 13% | Kernel forwarding at real WAN rates uses well under one core. The CPU-sensitive routing parts are **userspace**: daed proxy, DNS (daed→dnsmasq), pppd LCP, odhcpd, netifd. |
| NIC health | 7-day observe log on eth1: rx_missed 0→991, rx_no_buffer 65, time_squeeze 11 (ring 256) | It is unknown whether these correlate with CPU contention. Test as H2. |
| Desktop RT | No rtkit; gnome-shell logs "Failed to make thread 'KMS thread' high priority"; PipeWire runs without RT. With RT_GROUP_SCHED=y, cgroup v2 refuses SCHED_FIFO outside the root cgroup anyway | Optional track R (Phase 4) |
| Load profile | 7.7 h uptime, about 3% average CPU busy; one HDMI display connected; the archlinux VM is shut off | Contention is episodic, so a policy must cost nothing when idle. |
| Tools on router | python3, ucode, gcc/make, iperf3, tc, ethtool, podman, virsh, taskset. Missing: stress-ng, fio, irtt, perf (recipes exist in feeds/packages and package/devel/perf) | Prefer tools compiled on the device into /tmp and client-side tools. No packages are published for testing. |

### Mechanisms that set expectations (to be verified, not assumed)

- **cgroup v2 weights are hierarchical and relative among active siblings.** A background build in
  `user.slice` gets all of user.slice's top-level share when the desktop is idle. Lowering its
  weight inside user.slice therefore protects the **desktop**, not routing.
- **Group shares are spread across CPUs by load.** A slice saturating 4 CPUs has a per-CPU weight
  of about 256, while ksoftirqd (root cgroup, nice 0) or a single-threaded daemon has about 1024
  on its CPU. Expect routing to be starved of *share* rarely. The likely damage is *wakeup
  latency* (EEVDF slice ~2.1 ms, lazy preemption honoured at the next 10 ms tick on CPUs running
  user-mode hogs) and kernel-context/shared-cache interference. Work-conserving weights can do
  little about these.
- **Raising a top-level weight also deprioritizes root-cgroup kthreads** (ksoftirqd, napi, kswapd)
  relative to that slice. Default rule: demote expendable work, do not promote.
- These points suggest S will improve memory and OOM behavior and desktop-versus-background
  priority, but may do little for CPU-side routing latency. That residual is where a dynamic
  headroom governor could add value, which is exactly what Phase 1's lever sweep is designed to show.

### Hypotheses

| ID | Mechanism | Primary signal | Lever to test |
|---|---|---|---|
| H1 | Router userspace (daed, DNS, pppd) loses CPU share at equal weights | DNS p99, router-class probe wait, openwrt.slice `cpu.pressure` | S CPU classes; variant openwrt.slice=400 |
| H2 | Wakeup latency: lazy preemption at HZ=100 and ksoftirqd deferral behind hogs | router-class probe p99/p99.9, ksoftirqd schedstat run-delay, time_squeeze, NET_RX deferral | `cpu.idle` on aggressors; dynamic headroom (`cpu.max` or elastic `AllowedCPUs`) |
| H3 | Shared LLC, memory-bandwidth and kernel-lock interference (weights cannot help) | forwarding one-way p99, UDP loss at fixed load | non-work-conserving throttling (A only) |
| H4 | Memory pressure: router pages reclaimed or zram-swapped, kswapd competing with softirq, GFP_ATOMIC failures | memory PSI of router slices, rx_alloc_failed, DNS p99 | MemoryLow (S), oomd ordering (S), transient MemoryHigh on expendable work (A) |
| H5 | Background I/O stalls desktop page-ins (router daemons mostly write to tmpfs) | io PSI of session.slice, frame-late% | measure only; `io.max` via A if needed |
| H6 | Desktop competes equally with SSH builds and agents inside user-32769.slice | GTK frame-late%, desktop probe p99, session.slice `cpu.pressure` | session-scope weight (S) |
| H7 | Compositor and audio threads lack RT | frame-late% at moderate load, PipeWire xruns | track R (rtkit + `rt_group_sched=0`) |
| H8 | Heavy network load degrades the desktop | desktop metrics in N2 vs N0 | expected negligible at WAN rates; measured |

---

## 2. Architecture

### 2.1 Arms

| Arm | Contents | Runtime cost |
|---|---|---|
| B0 | The current image unchanged (the policy is installed but masked) | none |
| S | `openwrt-resource-policy`: unit drop-ins, oomd configuration, `bg-run` helper, `resource-policy-ctl` | zero daemons |
| A | S plus `resgovd` (C, sd-bus/sd-event) | target ≤0.1% of one core |
| R (optional, separate) | rtkit + `rt_group_sched=0` | needs a reboot per arm |

`resource-policy-ctl enable|disable|status` masks or unmasks every policy drop-in with
same-named `/dev/null` links in `/run/systemd/system/<unit>.d/`, which outrank `/usr/lib`, and then
runs `daemon-reload`. That gives fast, volatile arm switching for tests. `status` prints an **arm
fingerprint**: the effective `cpu.weight`, `cpu.idle`, `cpu.max`, `memory.low` and `AllowedCPUs`
of every governed cgroup, plus oomd state and governor state.

### 2.2 Workload classes and static policy S

Initial values are listed below. The lever sweep (Phase 1) tunes them before any A/B run, and
class membership is confirmed from `systemd-cgls` in Phase 0.

| Class | Members | CPU | Memory | OOM |
|---|---|---|---|---|
| Router-critical | openwrt-{network, dnsmasq, daed, passwall*, haproxy (Passwall balancing), odhcpd, firewall, wpad, sysntpd}.slice; openwrt-{ubusd, procd, services}.service, sshd, dbus, journald | default 100 (no promotion; variant S+ sets openwrt.slice=400) | MemoryLow = 1.5 × 7-day p99 of memory.current, set on each critical slice **and** on its ancestors (openwrt.slice, system.slice), because recursiveprot is off | oomd `ManagedOOMPreference=omit`; `OOMScoreAdjust=-900` on native units and on procd instance templates `openwrt-<svc>@.service.d/` if drop-ins apply to transient units (verify in VM) |
| Router-management | uhttpd, rpcd, uwsgi (LuCI) | 100 | small MemoryLow | omit |
| Auxiliary | openwrt-{samba4, nlbwmon, aria2, ddns-go}.slice; hermes-*, router-audit-collect, cockpit*, colord, upower, uci-history-events | CPUWeight=25 among siblings | — | default |
| Interactive | `user@UID.service` (session.slice: gnome-shell, pipewire, Xwayland; app.slice: apps, Sunshine, GRD) | 100 | MemoryLow on session.slice (p99 × 1.2) plus ancestors | session.slice omit; app.slice is a kill candidate |
| Normal compute | machine.slice VMs, rootful Podman (**user decision: normal**) | 100 | — | avoid |
| Background | logind `session-*.scope` (SSH and agents; **user decision: background**), user background.slice (30), `bg-run CMD` (→ background.slice), opt-in `machine-background.slice` (libvirt `<partition>/machine/background</partition>`, Podman `--cgroup-parent`) | session-*.scope CPUWeight=10 via prefix drop-in `session-.scope.d/`; machine-background 10; variant S-idle sets `cpu.idle=1` | — | killed first |

- **I/O:** no default change; `io.weight` would be ineffective. BFQ or iocost would each need
  their own A/B (BFQ costs CPU per I/O on the N5105; iocost needs a new kernel generation).
- **oomd:** enabled, with kill order background → app.slice → avoid VMs → never router-critical or
  GNOME core. `ManagedOOMSwap` stays at the 90% default as a last resort (hard to reach with zram).
- **Packaging:** `package/custom/openwrt-resource-policy/` installs drop-ins under
  `/usr/lib/systemd/system/*.d/60-resource-policy.conf` and the user-manager equivalents. Values
  derived from measurements live in one generated table (`files/policy.conf`) that the drop-ins come
  from at build time.
- **No change to:** kernel config, `/etc/config/network`, irqbalance, RPS/XPS, rings, coalescing,
  netdev sysctls, cpusets on router-critical work, top-level weights (unless variant S+ wins).

### 2.3 Adaptive governor A (`resgovd`): built only if gate G1 says so

**Purpose.** Keep CPU headroom for routing *only while* routing is active and other work is
contending, and give it back immediately afterwards. Static policy cannot express this, because
cpu.weight and cpu.idle are work-conserving and cannot keep a CPU idle for wakeups.

- **Inputs** (1 Hz timer plus PSI trigger fds for immediate wakeup; about 10 small reads per tick):
  - Routing activity and distress: per-CPU NET_RX softirq share (`/proc/stat`) and rate
    (`/proc/softirqs`); softnet `time_squeeze` and drop deltas; ksoftirqd `/proc/<pid>/schedstat`
    run-delay delta; igc `rx_missed_errors`; `cpu.pressure` and `memory.pressure` of the
    router-critical slices (PSI triggers such as `some 50000 1000000`).
  - Contention: `cpu.stat` usage and `cpu.pressure` of non-router classes, and the system idle
    fraction.
- **Decision.** Engage only if routing distress (thresholds from Phase 1 data) **and** contention
  (non-router classes use more than the reserve and idle capacity is below headroom H) hold for at
  least 2 s. Size H from router demand: clamp(1.5 × router p95 CPU + 0.25, 0.5, 2.0) CPUs.
  - Levels:
    - L1 caps background.
    - L2 also caps normal compute.
    - L3 also caps `app.slice`.
    - `session.slice` and router classes are never capped.
  - Step down one level after 20 s without distress. Minimum dwell is 10 s, and every action expires
    after 120 s unless re-confirmed.
- **Actuator**, picked by the lever sweep (exactly one):
  - (a) `CPUQuota` with a short `CPUQuotaPeriodSec` (20–50 ms; a 100 ms period causes stalls of up
    to 100 ms in VMs);
  - (b) elastic `AllowedCPUs` that leaves one CPU free (the CPU stays fixed rather than chasing
    irqbalance);
  - (c) toggling `cpu.idle`.
  - For memory, a transient MemoryHigh at 90% of current usage on background work under router
    memory PSI. This makes background tasks reclaim from their own pages instead of kswapd.
- **Safety:**
  - All changes go through `SetUnitProperties(runtime=true)` over sd-bus, never raw cgroupfs.
  - Only non-router classes are ever lowered. Floors: background ≥ 0.1 CPU, machine ≥ 2 CPUs.
  - Writes are rate-limited to at most 1/s. On startup the daemon resets to S.
  - `Type=notify`, `WatchdogSec=5s`, `Restart=on-failure`, and `ExecStopPost=/usr/libexec/resgov-reset`
    (restores S values).
  - `MemoryMax=16M`, `NoNewPrivileges`, `ProtectSystem=strict`.
  - `--shadow` mode logs decisions without acting.
- **Config and observability:** UCI `/etc/config/resgov` (enabled, shadow, thresholds), state in
  `/run/resgov/state.json`, one journal line per transition with the triggering signal values. The
  template is `package/custom/openwrt-needrestart` (C + libsystemd + unit).

### 2.4 Invariants (asserted by the harness on every run, for every arm)

- irqbalance is running with `-f -c 2 -t 10`.
- RPS masks, netdev sysctls, ring sizes, coalescing and the CAKE qdisc parameters are unchanged.
- No cpuset or limit is applied to router-critical cgroups or to the root cgroup.

---

## 3. Testbed and tooling

### 3.1 Topology (user decision: second NIC to eth2; nightly windows on the production router)

```
Debian host 192.0.2.165 (Ryzen 5700X3D)                Router N5105
 ns-lan : veth → br0 (enp42s0 is a br0 port) ── LAN ──── eth0/br-lan ─ fw4 + NAT + fullcone + flow offload + daed TCX
 ns-wan : USB 2.5GbE, rp-pppoe server (kernel mode) ───── eth2 → pppoe-bench (CAKE egress 130 Mbit, same options as pppoe-wan)
          test prefix 192.0.2.0/24 behind the PPPoE server: iperf3, irtt server, UDP sink
```

- Both endpoints run on one host and share one clock, so irtt gives **exact one-way forwarding
  delay**.
- eth2 is an igc port like eth1, so the path mirrors production LAN→PPPoE→CAKE.
- Router test config:
  - temporary `bench` interface and zone, sqm instance, and a daed direct rule for the test
    prefix (check that daed `wan_interface` binding and Passwall FakeDNS ranges do not overlap it);
  - applied under `uci-history --json begin --timeout 600 --note resbench` … `confirm`;
  - removed after each window.
- **Real-WAN confirmation**: a small subset run through the production pppoe-wan and daed proxy,
  using the existing Cloudflare client method from `bench.py`.
- **Client capacity calibration**: ns-lan↔ns-wan over a direct cable with no router, to find the
  client's maximum pps and Gbit. Offered loads stay ≤ 70% of client capacity (USB NIC pps is the
  likely limit).

### 3.2 Harness (new, in `scripts/resbench/`)

| File | Role |
|---|---|
| `resbench.py` | Controller on the Debian host: scenarios (`scenarios.json`), seeded randomized block schedule, arm switching over SSH (`sudo -n resource-policy-ctl`), aggressor lifecycle, invalidation, JSONL results. Ports the `snap`/`delta` logic from `/srv/openwrt-validation/steering-backup-20261031/bench.py` (per-CPU softirq/busy, NET_RX, IRQ effective affinity, softnet, `ethtool -S` misses, CAKE stats, RPS masks, pppoe ifindex). |
| `agent.py` | Router sampler at 1 Hz into `/run/resbench`: the bench.py snapshot plus cgroup `cpu.stat`/`cpu.pressure`/`memory.pressure`/`memory.current` per class, ksoftirqd and router-daemon schedstat, temperature (x86_pkg_temp), throttle counts, cpuidle residency, frequency, governor state, arm fingerprint. Copied to `/tmp` for each window; never installed. |
| `probe.c` | Wakeup-latency probe: absolute 4 ms `clock_nanosleep`, 0.3 ms of work, reports lateness histogram p50/p99/p99.9/max. Run in router-class (`openwrt-resbench.slice`), desktop (`app.slice`), session scope, and inside the bench VM. Compiled on the device with gcc into `/tmp`. |
| `aggressors/` | `memhog.c` (working set sized to push into zram), `iohog.c` (O_DIRECT random read/write on NVMe), `compile.sh` (pinned tarball, `make -j4` loop, counts finished objects/s), bench VM definition (small guest, 4 vCPU/1 GiB, fixed `xz -9` loop reporting ops/s over virtio-serial). |
| `frame-probe.js` | GJS GTK4 window with a continuous animation that logs frame-clock intervals. Reports frame-late% (>1.5× refresh) and p99 interval. Runs in the live HDMI session with screen blanking inhibited during the window. |
| `dnsprobe.py` | Constant-rate (200 qps) UDP DNS to 192.0.2.1 for names answered locally (router hostname, `.lan` PTR), so the path is daed→dnsmasq with no upstream. Reports p50/p99/timeouts. |
| `netns-setup.sh` | Builds ns-lan/ns-wan, the PPPoE server and test routes on the client, and tears them down. |
| `analyze.py` | Run-level statistics, paired bootstrap CIs, Wilcoxon, TOST, Holm correction, A/A-derived MDE, and Markdown tables for the validation doc. |
| `scripts/tests/test-resbench.py` | Host unit tests: delta math, invalidation rules, block randomization, and statistics on synthetic data with a known effect and with the null. |

Optional desktop metric: remote-stream frame delivery, reusing `scripts/tests/sunshine-stream-client.c`,
`sunshine-stream-probe.py` and `sunshine-stream-metrics.py` with an isolated test Sunshine
instance (never the user's pairing state).

### 3.3 Workloads

- **Network levels**
  - N0: probes only (irtt 2 ms interval, gateway ping, DNS 200 qps).
  - N1: N0 plus 50 Mbit mixed traffic.
  - N2: N0 plus 1 Gbit TCP downstream (8 streams) and upstream saturating CAKE at 130 Mbit.
  - N3: N2 plus UDP at a fixed offered pps of 90% of B0's uncontended lossless knee (64/512/1400 B
    mix).
- **Aggressors**
  - Wc: compile loop in an SSH session scope (background class).
  - Wv: bench VM (normal class).
  - Wd: frame-probe plus local 1080p video in Firefox (interactive).
  - Wm: memhog into zram.
  - Wio: iohog.

### 3.4 Scenarios (steady state: 30 s warm-up + 120 s measured; ~4 min per run with switching)

| ID | Network | Aggressors | Tests |
|---|---|---|---|
| S01 | N0 | — | idle latency floor, A overhead, no regression |
| S02 | N0 | Wc+Wv | **no tax on compute** (P4) |
| S03 | N1 | Wc+Wv+Wd | light-network mixed |
| S04 | N2 | — | no routing regression |
| S05 | N2 | Wc+Wv+Wd | **main contended case** (P1, P3) |
| S06 | N3 | Wc+Wv | **stress contended case** (P2) |
| S07 | N2 | Wm(+Wc) | memory pressure and oomd ordering |
| S08 | N2 | Wio+Wd | I/O |
| S09 | N1 | Wd+Wc | desktop against background |
| S10 | N2 | Wd | desktop under heavy network |
| T1 | step sequence N0→N2→N3→N1→N0 with staggered aggressors, 60 s per step, 30 min | | transitions, settling, oscillation |
| SOAK | 24 h, hourly synthetic pattern (10 min Wc, 5 min Wv, network bursts) | | stability, drift, leaks, flapping |
| WAN | production pppoe-wan + daed proxy, S04/S05 aggressors | | real-path confirmation |

### 3.5 Metrics

- **Routing**
  - Forwarded TCP goodput and retransmits.
  - UDP loss at fixed load.
  - One-way delay p50/p95/p99/p99.9 and loss (irtt).
  - Gateway RTT.
  - DNS p50/p99/timeout rate.
  - time_squeeze, backlog drops, NIC misses, CAKE drops (intentional shaping drops reported
    separately).
  - ksoftirqd run-delay; PPPoE LCP failures and reconnects.
- **Desktop:** frame-late%, p99 frame interval, desktop probe p99, `cpu/memory/io.pressure` of
  session.slice and app.slice, ssh echo RTT (interactive shell in the background class).
- **Compute:** compile objects/s, VM ops/s, memhog and iohog throughput, per-class CPU-seconds,
  system idle% while background work is runnable (the work-conservation check).
- **Governor:** CPU time, `memory.peak`, wakeups/s, io.stat writes, transitions/h, decision latency.

### 3.6 Experimental design and statistics

- **Randomized complete blocks.** One block runs every compared arm once for a scenario, in seeded
  random order. Blocks of different scenarios are interleaved within a night. Each run's unit of
  analysis is its summary statistic (for example per-run p99), never pooled packets.
- **Replication.** At least 5 blocks per night and at least 2 separate nights, so n ≥ 10 pairs per
  primary scenario. The schedule extends if MDE > threshold.
- **A/A first.** B0 against B0 for 10 blocks on S01/S05/S06 gives the per-metric noise and the
  minimum detectable effect (MDE ≈ 2.8·SD_diff/√n).
- **Tests.**
  - Improvement: paired bootstrap 95% CI of the Hodges–Lehmann difference plus a one-sided
    Wilcoxon test in the pre-declared direction, with Holm correction over the 4 primary endpoints.
  - "Close to baseline": TOST equivalence.
- **Pre-registration.** Criteria, scenarios and `analyze.py` are committed before the first S or A
  measurement, and the commit hash is recorded in the validation doc.
- **Thermal and steady-state control.** 10 min warm-up per window; record temperature, throttle
  counters, frequency and C-state residency per run.

### 3.7 Invalidation (pre-declared; invalid runs are re-queued at the end of the night and counted per arm)

- Production eth1 traffic above 20 Mbit average or 5 kpps.
- A thermal throttle count increment.
- Client CPU above 70%.
- An invariant or arm-fingerprint mismatch.
- A pppoe-wan or pppoe-bench reconnect, or an unrelated service restart.
- A tool error.
- A desktop that is locked or blanked during Wd.

If one arm is invalidated noticeably more often than the others, that is itself a finding.

---

## 4. Acceptance criteria (pre-registered)

**G0 (problem exists).** B0 degradation compares the contended scenario with the same network
level without aggressors. It is *material* if any of the following holds and exceeds the MDE:

- one-way p99 rises by more than max(1 ms, 50%);
- UDP loss at fixed load rises by more than 0.1 percentage points;
- TCP goodput falls by more than 5%;
- DNS p99 more than doubles, or timeouts exceed 0.1%;
- frame-late% rises by more than 5 percentage points.

Only hypotheses with material degradation get a lever. If there are none, stop.

**Primary endpoints (Holm family)**

| | Metric | Scenario |
|---|---|---|
| P1 | one-way forwarding p99 | S05 |
| P2 | UDP loss at fixed load | S06 |
| P3 | DNS p99 | S05 |
| P4 | total compute throughput (compile + VM) | S02, equivalence |

**Ship S over B0 when all of the following hold:**

1. **Routing gain.** At least one of P1–P3 improves significantly *and* recovers at least 50% of
   B0's contention-induced degradation for that metric. For example, if B0's p99 goes from 1.0 ms
   to 5.0 ms under contention, S must reach ≤ 3.0 ms.
2. **No tax when routing is idle or light.** P4 is equivalent within ±2% (TOST, 90% CI). In S01–S03,
   desktop metrics are no worse than B0 + 1 percentage point of frame-late%, and system idle% while
   background work is runnable is ≤ B0 + 1 percentage point.
3. **Proportional cost under contention (S05, S06).** The compute core-seconds lost compared with B0
   are at most 1.5 × the extra core-seconds received by routing (softirq plus router classes), plus
   2% of capacity. Desktop frame-late% ≤ B0 + 1 percentage point; desktop probe p99 ≤ 1.1 × B0 + 0.5 ms.
4. **No regression (S01, S04, S10).**
   - TCP goodput ≥ 98% of B0.
   - One-way p99 ≤ B0 + max(0.1 ms, 5%).
   - Gateway p95 and DNS p99 equivalent.
   - SSH echo p99 ≤ 2 × B0 in S09.
5. **Stability (all runs plus SOAK).**
   - 0 kernel warnings (RCU stall, BUG/WARN). The router kernel exposes no hung-task or
     soft-lockup sysctls, so those detectors are probably not built; stalls must show up in the
     probes (§3.2, §12.3).
   - 0 router-critical restarts, kills or failed units.
   - 0 PPPoE drops caused by the arm.
   - 0 oomd kills outside the background/app classes; S07 victim order matches §2.2.
6. **Repeatability.** The effect has the same sign and is significant on each night's half of the
   data. The real-WAN subset shows the same sign (significance is not required).

**Ship A over S:** criteria 1–6 hold with S as the reference, and in addition:

- **Overhead:** governor CPU ≤ 0.1% of one core when idle and ≤ 0.3% under load (24 h mean); RSS ≤
  4 MiB; ≤ 2 wakeups/s when idle; no disk writes beyond journal lines on transitions.
- **Dynamics:** in T1, at most 1 level change per step and settling within 5 s of a step. During
  SOAK steady phases, ≤ 6 transitions/h. In shadow mode, ≤ 1 false engagement per day with no
  distress present.
- **Failure safety:** after `kill -9`, SIGSTOP (watchdog), `daemon-reload` or `daemon-reexec` while
  at L2, all limits return to S within WatchdogSec + 1 s, with no routing-metric excursion.

Otherwise A is not shipped and the negative result is documented.

---

## 5. Implementation phases and gates

Each phase that touches the router needs explicit user authorization. Test-window changes use
uci-history and are reverted the same night.

### Phase 0: Harness and testbed (about 4 days of development, 1 night)

1. Keep this document (`docs/resource-governor-plan.md`) current: status line, gate outcomes, and
   any change to criteria made *before* measuring (never after).
2. Write `scripts/resbench/*` and `scripts/tests/test-resbench.py`, then run the host tests.
3. Client setup: install the USB 2.5GbE NIC, cable it to eth2, install `irtt` and `pppoe` from
   Debian, and run `netns-setup.sh`. Calibrate the client by cabling it directly to itself.
4. First router window:
   - bench topology through uci-history;
   - compile `probe.c` and the aggressors into `/tmp`;
   - define the bench VM;
   - measure B0's uncontended knee (pps and Gbit);
   - run A/A for 10 blocks to get MDE per metric.
5. Exit: A/A coefficient of variation is recorded, the MDE for P1–P4 is below the practical
   thresholds (otherwise lengthen runs or add blocks), and invariants hold across the night.

### Phase 1: B0 characterization, lever sweep, gate G0 (2 nights)

1. Run the full scenario matrix on B0 only, comparing contended with uncontended references. Map
   each degradation to a hypothesis using the agent signals (ksoftirqd delay against PSI against
   reclaim).
2. **Lever sweep** with manual `systemctl set-property --runtime` and nothing built. On S05/S06/S07/S09,
   compare:
   - (i) S CPU weights;
   - (ii) S-idle (`cpu.idle` on background);
   - (iii) S+ (openwrt.slice=400);
   - (iv) MemoryLow on router slices and ancestors;
   - (v) static `CPUQuota` 300% with a 20 ms period on non-router classes;
   - (vi) `AllowedCPUs=1-3` on non-router classes;
   - (vii) oracle: aggressors frozen with `cgroup.freeze`, which gives the upper bound any governor
     could reach.
3. G0 decides which hypotheses are real. The sweep quantifies the benefit each lever *could*
   deliver: weights against throttling against reservation against the oracle.
4. If the oracle recovers less than the MDE: stop, because no resource policy can help. If the
   residual comes from the preemption model (H2 under HZ=100/PREEMPT_LAZY) and no cgroup lever
   recovers it, report that a kernel change (HZ or preemption model, which needs a new kernel
   generation) is the real fix and propose it as a separate plan.

### Phase 2: Static policy S (about 2 days of development, a VM gate, 3 nights)

1. Create `package/custom/openwrt-resource-policy/`:
   - drop-ins only for the levers that Phase 1 justified;
   - `resource-policy-ctl`;
   - the `bg-run` wrapper;
   - oomd configuration.

   Then register it in `configs/custom-package-updates.json` (`provider: local`) and add the
   `configs/resource-policy.config` fragment.
2. **VM functional gate** with `scripts/tests/resource-policy-guest.py`, booting the exact image as
   `scripts/test-image-network.py` does. Check that:
   - drop-ins apply to implicit `openwrt-*.slice`, to procd transient `openwrt-<svc>@.service`
     (OOMScoreAdjust), and to logind `session-.scope` prefix drop-ins;
   - ancestors carry MemoryLow;
   - `resource-policy-ctl` masking round-trips;
   - procd restart and respawn and the service bridge still work (reuse the
     `systemd-cgroup-guest.py` and `procd-units-guest.sh` assertions);
   - oomd parses its configuration.
3. Choose the S variant (weights against `cpu.idle`; S against S+) on 5 pilot blocks using a rule
   declared in advance: the best P1–P3 result that passes guardrails 2–4.
4. Run B0 against S on the full matrix for 2 or more nights, plus WAN confirmation and SOAK (S).
5. **G1.** If S passes §4, S is shippable. Build A only if the Phase 1 sweep showed that a
   non-work-conserving lever (v/vi, or transient MemoryHigh) recovers a residual beyond S by at
   least the MDE in a primary endpoint. Otherwise skip to Phase 5.

### Phase 3: Adaptive governor A (about 5 days of development, 1 week in shadow, 3 nights + SOAK)

1. Write `src/resgovd.c`, the `openwrt-resgov.service` unit, `resgov-reset`, and UCI
   `/etc/config/resgov`, using the actuator chosen in Phase 1. Host unit tests
   (`scripts/tests/test-resgov.py`) compile the control logic with the host cc against fixture
   `/proc` and cgroupfs trees (as `test-gnome-rdp-audio-latency.py` does), covering:
   - hysteresis;
   - dwell and expiry;
   - floors;
   - rate limits;
   - reset on start and exit;
   - malformed input.
2. VM gate: fault injection (kill -9, SIGSTOP, daemon-reload, daemon-reexec, VM absent, a bad UCI
   value).
3. Router: one week in `--shadow` during normal use, to check the false-engagement rate and the
   transition rate.
4. Run S against A on the matrix plus T1 and SOAK (A) for 24 h. **G2** is the A criteria in §4.

### Phase 4 (optional, separate): Desktop RT track R

Pursue this only if, after S, frame-late% or PipeWire xruns in S09/S10 still fail the criteria.
It needs:

- a new custom package `rtkit`;
- `rt_group_sched=0` on the GRUB cmdline through kernelctl (or `CONFIG_RT_GROUP_SCHED_DEFAULT_DISABLED`,
  which needs a new kernel generation).

The block design runs across reboots. Also check that the RT compositor and PipeWire threads do
not hurt P1–P3, since RT threads outrank ksoftirqd.

### Phase 5: Ship and document

- `docs/resource-governor.md` (guide: classes, `bg-run`, opt-in VM background partition,
  `resource-policy-ctl`, recovery).
- `docs/resource-governor-validation.md`: image path and SHA256, a `| Check | Result |` table,
  primary endpoint CIs, a scope statement, and **Evidence** at
  `/srv/openwrt-validation/resource-governor-validation-YYYYMMDD/`.
- Update `package/base-files/system-description.systemd.md` and bump base-files PKG_RELEASE.
- Update the snapshot `configs/x86-64-systemd-desktop.config`.
- Commits: `resource-policy: …`, `resgov: …`, `docs: …`.
- Publication goes through `publish-changed-feeds.sh`. It is userspace-only; no new kernel
  generation is needed unless track R takes the config route. Physical install only with explicit
  authorization.

---

## 6. Negative outcomes and how each is detected

| Risk | Detection |
|---|---|
| Background weights or `cpu.idle` make SSH and agent TUIs laggy | session-scope probe, SSH echo p99 (S09) |
| Background starves indefinitely or priority inversion (lock holder in an idle or throttled group) | compile objects/s floor > 0 in every 10 s window; routing p99.9/max outliers and probe max lateness; journal RCU-stall and BUG/WARN messages |
| CFS throttling stalls VMs (cpu.max) | probe inside the VM (max lateness), guest dmesg soft-lockup and clocksource warnings |
| MemoryLow over-provisioned causes more zram swapping for desktop or VMs | memory.pressure of user@ and machine in S07; zram traffic |
| oomd kills the wrong cgroup, or too eagerly | S07 victim check; oomd journal; SOAK count |
| Governor flapping, misfiring on local SMB or Sunshine traffic, or reacting late | T1 transition counts and settling; shadow false-engagement rate; decision latency |
| Governor crash or hang leaves limits applied | Phase 3 fault-injection suite; arm fingerprint after each run |
| Policy interacts with irqbalance and shifts softirq load | per-CPU NET_RX share and effective-affinity distribution compared across arms; invariant asserts |
| Policy breaks procd, ubus or service-bridge management | VM functional gate; SOAK unit-failure count |
| Gains exist only in the synthetic topology | real-WAN confirmation must agree in sign |
| Thermal, C-state, client or household noise masquerades as an effect | covariates, invalidation rules, A/A MDE, randomized and interleaved arms |
| Slow regressions (leaks, drift) | 24 h SOAK trends of governor RSS, CPU and journal size |

## 7. Rollback

- **S at runtime:** `resource-policy-ctl disable`, which masks the drop-ins in `/run` and runs
  daemon-reload. It is volatile, so a reboot restores the installed policy.
- **S persistently:** `apk del openwrt-resource-policy && systemctl daemon-reload`. oomd alone:
  `systemctl disable --now systemd-oomd`.
- **A:** `systemctl disable --now openwrt-resgov`. ExecStopPost restores S values; runtime
  properties never survive a reboot; the package can be removed.
- **R:** select the previous GRUB entry or remove the cmdline parameter, then remove rtkit. The procd
  recovery entry stays available.
- **Testbed:** a uci-history revert of the bench interface, zone, sqm and daed rule; remove `/tmp`
  tools and the bench VM. The client runs `netns-setup.sh down`.
- **Failure containment:** neither S nor A touches router-critical cgroups, IRQ/RPS, sysctls or the
  kernel. The worst case is reduced compute capacity for expendable classes, and that is bounded by
  floors, expiry and reset.

## 8. Files

**New:**

- `docs/resource-governor-plan.md`, `docs/resource-governor.md`, `docs/resource-governor-validation.md`
- `scripts/resbench/{resbench.py, agent.py, probe.c, aggressors/, frame-probe.js, dnsprobe.py, netns-setup.sh, analyze.py, scenarios.json}`
- `scripts/tests/test-resbench.py`, `scripts/tests/resource-policy-guest.py`, `scripts/tests/test-resgov.py` (Phase 3)
- `package/custom/openwrt-resource-policy/` (Makefile, `files/` drop-ins, `resource-policy-ctl`, `bg-run`; Phase 3: `src/resgovd.c`, `openwrt-resgov.service`, `resgov-reset`, `resgov.config`)
- `configs/resource-policy.config`

**Modified:** `configs/custom-package-updates.json`, `configs/x86-64-systemd-desktop.config`,
`package/base-files/system-description.systemd.md` plus the base-files Makefile release.

**Reused:**

- `/srv/openwrt-validation/steering-backup-20261031/bench.py` (router snapshot and delta logic, Cloudflare client
  method)
- `scripts/test-image-network.py` (VM boot)
- `scripts/tests/systemd-cgroup-guest.py` and `procd-units-guest.sh` (placement assertions)
- `scripts/tests/sunshine-stream-*` (optional stream metric)
- `package/custom/openwrt-needrestart` (C + libsystemd package template)
- systemd-oomd (already built)
- uci-history (test-window changes)
- router-audit history (7-day memory p99 for MemoryLow sizing)

## 9. Verification summary

1. Host: `python3 scripts/tests/test-resbench.py`, `python3 scripts/tests/test-resgov.py`,
   `git diff --check`.
2. Build: `make package/custom/openwrt-resource-policy/compile V=s`, an image build, and
   `scripts/deptest.sh openwrt-resource-policy`.
3. VM: `resource-policy-guest.py` plus the Phase 3 fault-injection suite on the exact image.
4. Router (authorized windows): A/A, B0 matrix and lever sweep, B0 vs S, (S vs A), T1, SOAK,
   real-WAN subset. Run `analyze.py` to produce the §4 verdict tables into the validation doc.

## 10. Out of scope and possible follow-ups

- IRQ affinity, RPS/XPS, irqbalance, rings and coalescing (preserved).
- Threaded NAPI, sched_ext, PM QoS and C-state limits (C3 exit latency of 1 ms dominates *idle*
  latency; that is a power/latency trade-off for a separate A/B).
- Kernel HZ or preemption model, and IRQ_TIME_ACCOUNTING. Recommend these only if Phase 1 attributes
  the residual to them.
- LuCI UI.

## 11. Housekeeping noticed (not acted on)

The root crontab still has the hourly
`/srv/openwrt-validation/steering-backup-20261031/verify.sh … # steering-observe (remove after 2026-11-01 20:00)`
entry, six days past its removal date. Its log also shows the eth1 rx_missed growth used as
evidence in H2. The user should decide whether to remove it.

---

## 12. Handoff notes for the implementing agent

Notes collected while planning (2026-11-07) that are not obvious from the code. Router facts
drift, so re-run the §12.3 probe before relying on any number here.

### 12.1 Decisions and rules already settled

| Topic | Decision |
|---|---|
| Testbed | A second 2.5GbE NIC on the Debian host (USB is acceptable), cabled to the router's unused `eth2`, with an emulated PPPoE + CAKE WAN on it (§3.1). |
| Where tests run | On the production router, in scheduled night windows of about 3–4 h. Runs disturbed by household traffic are invalidated, not dropped (§3.7). |
| SSH login sessions | Background class (lower weight than the GNOME session). This includes coding agents that run over SSH. |
| VMs and rootful containers | Normal class by default, with per-VM/container opt-in to `machine-background.slice`. |
| Authorization | Every step that touches the router (test topology, tools copied to `/tmp`, policy arms, VM definitions) needs the user's explicit go-ahead for that window. Feed publication and physical installation also need explicit authorization (`AGENTS.md`, `CLAUDE.md`). |
| UCI changes on the router | Always inside `uci-history --json begin --timeout 600 --note '…'`, then verify and `uci-history --json confirm` (CLAUDE.md, "Changing router configuration"). Never paste `--show-secrets` output. |
| Never change | irqbalance and its arguments, RPS/XPS masks, IRQ affinities, ring sizes, coalescing, `net.core.*` budgets/backlog, CAKE parameters, the kernel config (outside optional track R). |
| Commits | Commit only when the user asks. Use focused `area: summary` subjects (`resbench: …`, `resource-policy: …`, `resgov: …`, `docs: …`) and stage explicit paths. Never commit `files/` beyond its 11 tracked files. |

### 12.2 Verified in source on 2026-11-07

- **Fair-class wakeup preemption is always lazy on this kernel.**
  - In `build_dir/target-x86_64_glibc/linux-x86_64/linux-7.3.3/kernel/sched/fair.c`,
    `wakeup_preempt_fair()` ends every preemption path in `resched_curr_lazy()`. That includes
    "non-idle wakee preempts an idle entity", so `cpu.idle` changes the *decision*, not how
    quickly it is delivered.
  - `kernel/sched/core.c` `__resched_curr()` sends **no IPI** for the lazy bit on a remote CPU.
    `sched_tick()` upgrades a pending lazy bit to a full resched, and exit to user mode honours both
    bits.
  - With HZ=100, a router daemon woken onto a CPU that is running a hog can therefore wait up to
    about 10 ms, unless that CPU takes an interrupt or makes a syscall first. This is the mechanism
    behind H2. The `probe.c` design (router-class lateness percentiles) measures it directly.
  - Scheduler features on: `PLACE_LAG`, `RUN_TO_PARITY`, `PREEMPT_SHORT`. Off: `NEXT_BUDDY`.
  - `PREEMPT_SHORT` makes a **shorter custom slice** (`sched_attr.sched_runtime` for SCHED_OTHER)
    preempt sooner. That is a cheap extra lever worth adding to the Phase 1 sweep. Check whether the
    router's util-linux `chrt` can set it; otherwise use a 20-line `sched_setattr` helper.
  - None of this changes the lazy delivery itself. Only the preemption model or HZ does that, and
    both are kernel changes (§10).
- **cgroup2 mount options.**
  - procd's early init mounts cgroup2 with only `nsdelegate`. This is upstream procd code, visible as
    a context line in `package/system/procd/patches/100-systemd-compatibility.patch`. systemd does
    not remount it.
  - So `memory_recursiveprot` is off. `MemoryLow` on a leaf gives no protection unless every
    ancestor also has `memory.low` ≥ the child's value.
  - The plan sets ancestors explicitly. Adding `memory_recursiveprot` for native systemd boots
    would be a procd base change with its own validation. Do not slip it in.
- **Drop-in resolution.** systemd 262 (`build_dir/target-x86_64_glibc/systemd-262/src/shared/dropin.c`)
  walks the "-" prefix chain, so `session-.scope.d/` should match logind `session-cN.scope`.
  Whether drop-ins (OOMScoreAdjust) apply to procd's **transient** `openwrt-<svc>@<inst>.service`
  units, and to slices that procd only references by name, is **unverified**. Test both in the
  Phase 2 VM gate before relying on them. If they don't apply, OOMScoreAdjust needs a small procd
  patch (an instance parameter mapped to the transient property). That is a separate, reviewed
  change.
- **Where procd puts things.** `130-systemd-transient-units.patch` sets `Slice=openwrt-<svc>.slice`,
  `TasksMax=infinity`, `OOMPolicy=continue` and `Nice` (from the instance), plus rlimits. It sets no
  CPU, memory or OOM-score property. `openwrt.slice` (from `package/system/systemd-openwrt/files/openwrt.slice`)
  sets only `TasksMax=infinity`.

### 12.3 Read-only router probe (re-run before relying on §1)

Access is `ssh -o BatchMode=yes router-admin@192.0.2.1`, with `sudo -n` for root-only reads. All of
the following is read-only:

```sh
uname -r; free -m; cat /proc/swaps; cat /proc/cmdline
cat /sys/fs/cgroup/cgroup.subtree_control /sys/fs/cgroup/user.slice/cgroup.subtree_control
findmnt -no OPTIONS /sys/fs/cgroup                      # expect nsdelegate only
cat /proc/pressure/{cpu,memory,io}
zcat /proc/config.gz | grep -E '^CONFIG_(HZ|PREEMPT_LAZY|RT_GROUP_SCHED|PSI|IRQ_TIME_ACCOUNTING|BLK_CGROUP_IO.*)='
pgrep -a irqbalance                                      # expect -f -c 2 -t 10
for d in /proc/irq/[0-9]*; do ls $d | grep -q eth && echo "$(basename $d) $(cat $d/effective_affinity_list) $(ls $d | grep eth)"; done
for i in eth0 eth1 eth2; do echo $i $(cat /sys/class/net/$i/queues/rx-*/rps_cpus | sort -u); done
sysctl net.core.netdev_budget net.core.netdev_budget_usecs net.core.netdev_max_backlog
uci show sqm.wan; uci -q show 'firewall.@defaults[0]' | grep -E 'flow_offloading|fullcone'   # quote the @ under zsh
systemd-cgtop -b -n 2 -d 2 --depth=3
for u in system.slice user.slice machine.slice openwrt.slice; do systemctl show $u -p CPUWeight -p MemoryLow -p ManagedOOMMemoryPressure; done
ps -eLo pid,tid,cls,rtprio,ni,comm | awk '$3!="TS"'      # RT/batch threads
cat /sys/devices/system/cpu/cpu0/cpuidle/state*/{name,latency}
sudo -n cat /sys/kernel/debug/sched/base_slice_ns       # 2100000 on 2026-11-07
sudo -n crontab -l; systemctl list-timers --all --no-pager
loginctl list-sessions --no-legend
```

Snapshot values from 2026-11-07:

- **Sessions:** `c3` is hnt510's GNOME session (seat0, tty7). `c9` and `c927` are SSH sessions
  (opencode ran in `c9`). Two user managers are running: desktop-user (uid 32769) and `aria2`
  (uid 32771).
- **Memory by cgroup:** openwrt.slice 322 MiB in total: daed 145 MiB, passwall_server 50 MiB,
  haproxy 20 MiB, ddns-go 17 MiB, samba4 23 MiB, network 5 MiB.
- **SQM (`sqm.wan`)** — mirror these settings exactly on the bench sqm instance:

  | Option | Value |
  |---|---|
  | `interface` | `pppoe-wan` |
  | `download` | `0` |
  | `upload` | `130000` |
  | `qdisc` / `script` | `cake` / `piece_of_cake.qos` |
  | `ingress_ecn` / `egress_ecn` | `ECN` / `ECN` |
  | `itarget` / `etarget` | `auto` / `auto` |
  | `linklayer` | `ethernet` |
  | `overhead` / `tcMPU` | `44` / `84` |
  | `linklayer_adaptation_mechanism` | `cake` |
  | `eqdisc_opts` | `dual-srchost split-gso` |
  | `use_mq` | `0` |
  | `qdisc_advanced` / `qdisc_really_really_advanced` | `1` / `1` |

- **Kernel tunables:** `sched_rt_runtime_us` reads 1000000. Neither `kernel.hung_task_*` nor
  `kernel.softlockup_panic` exists, so the hung-task and soft-lockup detectors are probably not
  built. Do not rely on them to detect stalls; use probe max-lateness.
- **Scheduler stats:** `/proc/<pid>/schedstat` works (fields: run ns, wait ns, slices). The
  `kernel.sched_schedstats` sysctl is absent; per-task wait time is still available.

### 12.4 The existing steering benchmark (reuse, do not modify in place)

**Files.** Everything is on the router under `/srv/openwrt-validation/steering-backup-20261031/` (root-only):

- `bench.py`, the program the user calls the dedicated testing program;
- `verify.sh`, which writes `observe-24h.log` from an hourly cron at :17;
- `ethtool.txt`, `irq-affinity.txt`, and `network.conf` (mode 0600, may contain secrets: do not
  print it);
- `results-r1-3.jsonl`, the valid three rounds;
- `results-429-invalid.jsonl` (Cloudflare rate-limited) and `results-failed-ssh.jsonl`.

Its methodology and acceptance style are written down in `/srv/openwrt-validation/router-optimization-plan.md` on
the router: median throughput within 5%, loaded p95 latency no worse than max(2 ms, 10%), three
rounds with the profile order rotated.

**How it runs.** `bench.py` runs on the router as root. It drives the Debian client over
`sudo -u desktop-user ssh admin@192.0.2.165 'python3 /tmp/cfclient.py PHASE DUR STREAMS'`, and
**`/tmp/cfclient.py` no longer exists on the client**, so it must be rewritten. Its output is one
JSON line per phase:

- `phase`, `t0`, `dur`, `mbps`, `errors`, `nerr`;
- `gw{n,sent,p50,p95,max}` (latency to 192.0.2.1, in ms);
- `cf{…}` (latency to Cloudflare).

**Profiles.**

| Profile | eth0 RPS | eth1 RPS | Note |
|---|---|---|---|
| base | `3` | `1` | |
| A | `f` | `f` | current production state |
| B | `0` | `f` | |

irqbalance stayed running throughout.

**Valid-round results.**

- Gateway latency: p50 0.3–0.45 ms idle versus about 0.15 ms during transfers; p95 0.5–0.6 ms idle.
  C-state exit latency explains why idle is worse.
- Throughput: download 114–210 Mbit/s, upload 113–148 Mbit/s (CAKE caps at 130).
- CPU: softirq ≤ 6.7% per CPU, busy ≤ 12.9%.
- No backlog drops, time_squeeze or hardware misses during the runs.
- Cloudflare RTT was about 200–240 ms, so that traffic goes through the daed proxy path.

**What to port.** Bring its `snap()`/`delta()` into `scripts/resbench/agent.py`. They cover
`/proc/stat`, NET_RX from `/proc/softirqs`, interrupts with effective affinity,
`/proc/net/softnet_stat`, `ethtool -S` miss counters, CAKE bandwidth and drops, RPS masks, and the
pppoe ifindex as a reconnect detector.

### 12.5 Testbed pitfalls

- **Client (Debian, 192.0.2.165, Ryzen 7 5700X3D, 16 threads).**
  - `enp42s0` (2.5G) is a **port of `br0`**, so macvlan on it will fail. Attach ns-lan with a
    veth pair into `br0`.
  - Docker bridges occupy 172.17–172.21/16; keep test prefixes away from them.
  - The host also runs the router-analyzer services and containers. Pin the load generators with
    `taskset` and record client CPU on every run (invalidate above 70%).
  - Calibrate USB NIC pps first; it is likely the client-side ceiling.
- **Test prefix and daed.**
  - daed attaches TCX programs to the LAN and hijacks LAN DNS. Its configuration is managed by
    daed itself (web UI on `:2023`, state under `/etc/daed`), not UCI.
  - The bench prefix (proposed 192.0.2.0/24) needs a temporary **direct** routing rule. Confirm
    test flows are direct through daed's log or router-audit `conn_flows` before measuring.
  - Check whether daed's `wan_interface` would attach to the new `pppoe-bench`.
  - Avoid 198.18.0.0/15: it is the usual Passwall/sing-box FakeDNS pool.
  - Export daed's configuration before the change and restore it afterwards.
- **Router ports.** `eth2` and `eth3` are igc with no link and no configuration. The bench
  `pppoe-bench` interface on `eth2` must use a separate firewall zone with masquerade. Fullcone
  and flow offload come from the global defaults, as in production.
- **Desktop measurements** run inside the user's live GNOME session (HDMI-A-1 connected).
  - Frame callbacks stop when the screen locks or blanks. Inhibit idle for the window
    (`gnome-session-inhibit --inhibit idle …` or a temporary `idle-delay`), then restore it.
  - Never touch the user's Sunshine pairing state; the stream metric needs an isolated Sunshine
    instance.
- **Noise sources on the router.**
  - `hermes-gateway`/`hermes-dashboard` (about 1.5% CPU) and `hermes-readonly-refresh.timer`
    (every minute).
  - `router-audit-collect`, `uci-history-sweep.timer` (15 min) and `openwrt-journal-rotate.timer`.
  - The stale steering-observe cron at minute :17 (§11).
  - Coding agents working on the router over SSH. Check `loginctl list-sessions` and session-scope
    CPU at the start of every run, and invalidate if an agent is active.
- **Router tools.** The router has gcc, make and python3, but no stress-ng, fio, irtt or perf.
  - Compile the small C tools on the device into `/tmp`. `/tmp` is tmpfs, so tool files count as
    shmem; keep them small and identical across arms.
  - Do not install packages from the LAN feed just for testing.
- **Bench VM.** Do not use the user's `archlinux` VM. Define a dedicated bench VM; there is
  55 GiB free on the overlay.
- **Unconfirmed until read as root.** `uci show network.globals` returned nothing without root.
  The repo overlay has `packet_steering '1'`, while every queue shows RPS `f`; read it as root
  before treating either as the source of truth.

### 12.6 Packaging and publication reminders

- Register `openwrt-resource-policy` in `configs/custom-package-updates.json` with
  `"provider": "local"`. Otherwise `./scripts/feeds update` fails.
- Published APK identities are immutable: any change to the bytes needs a new `PKG_RELEASE`.
- For a shipped feature, update `package/base-files/system-description.systemd.md` and bump
  base-files (user preference).
- Write the guide and validation pair in English, like the neighbouring systemd docs. The
  validation record is hand-written, with the image SHA256, a `| Check | Result |` table, a scope
  statement and an Evidence path outside the repo.
- Production publication only goes through `scripts/publish-changed-feeds.sh`, which needs a
  reachable router and a passing preflight. Never install on the router directly unless the user
  authorizes it.

### 12.7 Open questions to settle early in Phase 0

1. USB 2.5GbE adapter model, and whether the user already has one (r8152-class adapters top out
   well below line rate at small packet sizes).
2. The first night window, and whether the user wants the stale steering-observe cron removed
   first.
3. The pinned compile workload source (a fixed tarball checked into the evidence directory, not
   fetched at run time).
4. A bench VM image (a small Debian or Alpine cloud image, checksum recorded).
5. Whether `chrt` on the router supports SCHED_OTHER custom slices (for the PREEMPT_SHORT lever).
6. The ISP downstream capacity (`sqm.wan.download=0`, so it is unshaped). This is needed to choose
   a realistic N2 level for the real-WAN subset.

### 12.8 Suggested order for the first implementation session

1. Re-run §12.3 and update §1 if anything drifted.
2. Write `scripts/resbench/` and `scripts/tests/test-resbench.py`. This is host-only work and needs
   no router access. Get `analyze.py` right first, tested on synthetic data with a known effect and
   with the null, because every later gate depends on it.
3. Ask the user for the §12.7 answers and the first window.
4. Phase 0, step 4 (topology, calibration, A/A), then Phase 1. Record G0 in the status line.

**Rough budget:**

| Phase | Router time | Development |
|---|---|---|
| 0 | 1 night | about 4 days |
| 1 | 2 nights | — |
| 2 | 3 nights + 24 h soak | about 2 days |
| 3 (only if G1 says so) | 1 week shadow + 3 nights + 24 h soak | about 5 days |
