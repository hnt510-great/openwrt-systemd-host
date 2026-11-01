# daed validation

Validated on 2026-11-01 on the build host. The image was built with
`python3 scripts/build-and-publish.py build-only -j12`, which reserved kernel
generation 45 (`7.3.1-owrt-d4c77a6d354d9d21248f93d7f68211ce-r1-g45`); nothing
was published at build time; publication followed separately (see
Publication). (Sequence 44 was reserved by an aborted invocation and never
built or published.) All runtime checks ran in disposable KVM guests; **no
physical device was flashed or upgraded**.

## Artifacts

| Artifact | SHA256 |
| --- | --- |
| `openwrt-x86-64-generic-squashfs-combined-efi.img.gz` (generation 45) | `0541c0264fbd167e226c2d72fd0c0820307361544194ce5bbd9551587ab3ee19` |
| `daed-2.1.1-r1.apk` | `1c054331926e48d1414795223dfecd1a7e569e278b7db1478ef3abe957dffaae` |
| `daed-geoip-2.1.1-r1.apk` | `76cd35776fec6fbfc5a375a63fb055dcabf2ca72d745617e8f1d968f683d0651` |
| `daed-geosite-2.1.1-r1.apk` | `77f1ae2137e694fc9c4c348ffb7ed8b63a495697b0af4623f16ac7e808e5803f` |
| `kmod-sched-bpf-7.3.1-owrt-d4c77a6d…-r1-g45-1000.45.7.3.1-r1.apk` | `fa30ad41cc0c477026db4ad546b108bccb3cca5455a18cad54a5845e967c8d76` |

## Sources

| Input | SHA256 / identity |
| --- | --- |
| dae-wing `b089b568649f03f909477adb6c7db25535a58782` (codeload tarball) | `406119814907ea34dfa935b6f1ba925d887992e351da746f1ff7a206a6f2a21b` |
| dae v2.1.1 `dae-full-src.tar.xz` | `7c91494a999a24e91869e8e20e26ed8171dd4eedbcb847d1b04d15a6aeb54f44` (matches the GitHub asset digest) |
| daed v2.1.1 `web.zip` | `7eb8f42d4860ab7311f87bda2a921bad34a6d54db7edad47466dcb8d9382fea8` (matches the GitHub asset digest) |

## Source and build checks

| Check | Result |
| --- | --- |
| Pinned core of the daed v2.1.1 release | dae-wing `dc50308` → dae `85a1fc3` (2026-04-22, 30 commits before dae v2.1.1) |
| Cherry-picking every dae commit `85a1fc3..v2.1.1` onto that core | All code applies; only CI/docs files and `go.mod`/`go.sum` conflict. Result equals the `v2.1.1` tree apart from `go.mod`/`go.sum` and two docs files, so the fixes cannot be separated from the core upgrade |
| `dae-full-src.tar.xz` against `git archive v2.1.1` | Identical apart from the added `control/kern/headers` submodule |
| dae-wing `b089b56` with the unpatched v2.1.1 core | Does not compile: `marshaller.Bytes undefined`; fixed by patch 001 (dae `6f2f2aa`) |
| Patches 001–003 (dae `6f2f2aa`, `fb5eae6`, `e3fee8f`) on the v2.1.1 core | Code hunks apply without conflict; only docs/changelog hunks conflicted and were dropped; refreshed with `make package/daed/refresh` |
| GraphQL schema, daed v2.1.1 backend versus the re-pinned backend (`daed export schema`) | Only `Global`/`globalInput` differ: `soMarkFromDaeSet` removed; `disableThp`, `autoSniffPunt`, `bpfConnStateMapSize` added |
| daed v2.1.1 dashboard sources (`apps/web`) against the new schema | Never uses `soMarkFromDaeSet`; every `global` field queried exists |
| Replay of `Kernel/Configure/Default` with the new knobs, then `listnewconfig` | No new unanswered symbols; generic `config-7.3` unchanged |
| `make tools/llvm-bpf/compile` | Pass (LLVM 22.1.3, built once) |
| `make target/linux/compile` | Pass; vermagic `2f47df10…` → `d4c77a6d…` |
| Built kernel `.config` | `DEBUG_INFO_BTF=y`, `DEBUG_INFO_BTF_MODULES=y`, `# DEBUG_INFO_REDUCED is not set`, `MODULE_ALLOW_BTF_MISMATCH=y`, `BPF_STREAM_PARSER=y`, `NETKIT=y`, `NET_CLS_BPF=m`, `NET_ACT_BPF=m` |
| `make package/daed/compile` | Pass; `daed` is a static x86-64 ELF, `daed --version` → `daed version 2.1.1`; Go modules fetched through the module proxy |
| `python3 scripts/tests/test-custom-package-updates.py` | 47 tests pass (includes `.zip` sources and `companion_assets`) |
| `python3 scripts/update-custom-packages.py --check --package daed` | `daed: local` |
| `git diff --check` | Clean |

## Size impact

| Item | Generation 43 | Generation 45 |
| --- | --- | --- |
| `bzImage` | 8,221,696 bytes | 9,556,992 bytes (+1.27 MiB) |
| `.BTF` section in `vmlinux` | none | 5,632,364 bytes (uncompressed) |
| Generation kmod APKs | 253 packages, 11,962,785 bytes | 254 packages (+`kmod-sched-bpf`), 14,283,112 bytes (+2.2 MiB, split module BTF) |
| `daed-2.1.1-r1.apk` | — | 25,185,653 bytes (binary with embedded dashboard and BPF objects) |

## VM checks

`python3 scripts/test-image-network.py` (existing gate, daed disabled):
**passed** — `native-init`, `router-services`, `wan-dhcp`, `lan-dhcp`, `dns`,
`routing-nat`, `luci-auth`, `luci-http`, `ubus-board`; guest kernel
`7.3.1-owrt-d4c77a6d354d9d21248f93d7f68211ce-r1-g45`.

`python3 scripts/tests/test-daed-vm.py` (run 6, **passed**). Router and
client boot the exact image; the router's WAN is a restricted QEMU network
with a direct HTTP target (`10.203.0.100`) and a fake SOCKS5 node
(`10.203.0.101`); `10.203.0.102` exists only behind the proxy. daed is
configured through its GraphQL API (`br-lan` bound, `dip(10.203.0.102/32) ->
proxy`, `fallback: direct`, DNS `fallback: asis`).

| Check | Result |
| --- | --- |
| `/sys/kernel/btf/vmlinux` present | Pass |
| `/proc/config.gz`: BTF, stream parser, netkit, `cls_bpf`, `sch_ingress` | Pass |
| `daed --version`, `/usr/share/dae/{geoip,geosite}.dat` resolve | Pass |
| Disabled by default (`enabled '0'`, no process) | Pass |
| Firewall default `flow_offloading '1'` from the image overlay, flowtable active | Pass |
| Passwall enabled → `daed` refuses to start and logs the reason | Pass |
| Dashboard reachable from the LAN client on port 2023; `input_wan` ends in reject | Pass |
| Hooks: tcx links on `br-lan` | Pass (2 links); `dae0` is a netkit pair |
| Direct route (3 requests to `10.203.0.100`) | Pass |
| Proxy route (`10.203.0.102` answered by the SOCKS5 node) | Pass |
| DNS from the client to the router through dae (`asis` to dnsmasq) | Pass |
| `conf/all/send_redirects` and `conf/br-lan/send_redirects` both `0` (patch 003) | Pass |
| Enabling Passwall plus a `config.change` event stops daed | Pass |
| After stop: no tcx links, no `dae0`; proxy-only address unreachable; direct works | Pass |
| `start` again resumes the selected configuration (proxy route works) | Pass |
| One-shot `next_entry=owrt-rescue-procd` boot: PID 1 is `procd`, `openwrt.init=procd` | Pass |
| procd boot: daed autostarts with the saved configuration (tcx links present) | Pass |
| procd boot: direct and proxy routes | Pass |
| procd boot: stop removes links and `dae0` | Pass |

Runs 1–5 failed on test-harness assumptions that were then fixed: run 1
expected `tc` filters (dae uses tcx links on Linux 7.3), runs 3–5 located the
boot entry wrongly (kernelctl owns `grub.cfg`; the test now uses GRUB's
`next_entry`). No product change was needed between runs.

## Scope

- Not covered: real proxy protocols (only SOCKS5 against a local fake node),
  UDP proxying, IPv6, binding the WAN device, PPPoE, hardware offloading,
  physical NICs, long-running stability and memory use, the dashboard UI in a
  browser (only the HTML index and the GraphQL API were exercised), and an APK
  upgrade from generation 43 on a router.
- Installation on the physical router was not performed (see Publication).

## Publication

Published on 2026-11-01 with `scripts/publish-changed-feeds.sh` from the
same build tree; no packages were installed on the router.

| Check | Result |
| --- | --- |
| Router upgrade preflight (`desktop-user@192.0.2.1`, baseline ABI `7.3.1~2f47df105af5f7d3cac5e3b7f5fd2bee-r1`) | Passed; userspace and target-ABI simulations `full`/`passed`, no blockers |
| Userspace snapshot | `/srv/openwrt-feeds/public/snapshots/20261101T024109.091311Z` (daed APKs in `base/` and `custom/`, byte-identical, as for other custom packages) |
| Kernel snapshot | `/srv/openwrt-feeds/public/kernel-snapshots/1793500924785524813`, generation `7.3.1-owrt-d4c77a6d354d9d21248f93d7f68211ce-r1-g45` |
| Receipt | `/srv/openwrt-feeds/upgrade-receipts/1793500991307529129.json` (`passed`) |

## Evidence

`/srv/openwrt-validation/daed-validation-20261101/`: the exact image,
`network/validation.json`, `daed-run{1..6}/validation.json` with per-guest
command and serial logs. Build logs are in `logs/daed/` of the build tree.
