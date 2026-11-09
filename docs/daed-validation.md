# daed validation

Validated on 2026-11-01 on the build host. The image was built with
`python3 scripts/build-and-publish.py build-only -j12`, which reserved kernel
generation 45 (`7.3.1-owrt-d4c77a6d354d9d21248f93d7f68211ce-r1-g45`); nothing
was published at build time; publication followed separately (see
Publication). (Sequence 44 was reserved by an aborted invocation and never
built or published.) All runtime checks ran in disposable KVM guests; no physical device was
flashed. Packages were later installed on the router at the user's request
(see LuCI app).

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
| Router upgrade preflight (`builder@192.0.2.1`, baseline ABI `7.3.1~2f47df105af5f7d3cac5e3b7f5fd2bee-r1`) | Passed; userspace and target-ABI simulations `full`/`passed`, no blockers |
| Userspace snapshot | `/srv/openwrt-feeds/public/snapshots/20261101T024109.091311Z` (daed APKs in `base/` and `custom/`, byte-identical, as for other custom packages) |
| Kernel snapshot | `/srv/openwrt-feeds/public/kernel-snapshots/1793500924785524813`, generation `7.3.1-owrt-d4c77a6d354d9d21248f93d7f68211ce-r1-g45` |
| Receipt | `/srv/openwrt-feeds/upgrade-receipts/1793500991307529129.json` (`passed`) |

## LuCI app

`luci-app-daed` was added afterwards and validated on a rebuilt image (same
kernel generation 45; userspace only).

| Artifact | SHA256 |
| --- | --- |
| `openwrt-x86-64-generic-squashfs-combined-efi.img.gz` (with `luci-app-daed`) | `5aa1ae750fad579d35dd642be5ffa07a25070b985d494206828dacbb36ca819b` |
| `luci-app-daed-1.0.0-r1.apk` | `77b25b9a7157a371cb3e9250191b8946a76ea10c37f7f9361f99a07c5d73d0b3` |

| Check | Result |
| --- | --- |
| `node scripts/tests/test-luci-daed-view.js` | Pass |
| `msgfmt -c` on `po/zh_Hans/daed.po` | Pass |
| `test-image-network.py` (daed disabled) | Pass, 9/9 |
| `test-daed-vm.py`, all checks above | Pass (run 6 in `luci/`) |
| Restricted login (`luci-base` + `luci-app-daed`) reads `daed` config | Pass |
| Same login: `file.exec` of the tail command returns the daed log | Pass |
| Same login: `file.exec /bin/sh -c id` | Denied |
| Same login: `uci set enabled=0` + `uci apply` stops daed; `enabled=1` + `uci apply` starts it and the proxy route works | Pass |
| Same login: `file.exec /etc/init.d/daed restart` | Pass |
| `view/daed/settings.js` served by uhttpd; menu entry `admin/services/daed` installed | Pass |

Published on 2026-11-01 with `scripts/publish-changed-feeds.sh` (router
preflight passed, no blockers; kernel generation unchanged): userspace
snapshot `/srv/openwrt-feeds/public/snapshots/20261101T040201.881442Z`,
receipt `/srv/openwrt-feeds/upgrade-receipts/1793505816101772489.json`. The
published `luci-app-daed-1.0.0-r1.apk` is the validated file above;
`luci-i18n-daed-zh-cn-26.305.10562~143b772.apk` was published with it.

`luci-app-daed-1.0.0-r2` replaces the dashboard button with an
always-visible link (`node scripts/tests/test-luci-daed-view.js` passes; no
ACL or backend change, so the VM run was not repeated). It was published
with `luci-i18n-daed-zh-cn-26.305.16552~7c0a417` (snapshot
`20261101T043732.754745Z`, receipt `1793507914818866019.json`, preflight
passed) and, at the user's request, installed on the router with
`sudo apk upgrade` (1.0.0-r1 → r2). The router had `daed` 2.1.1-r1,
`daed-geoip`, `daed-geosite`, `luci-app-daed` and `kmod-sched-bpf` installed
earlier the same day by `sudo apk add`, also at the user's request; daed
remains disabled (`enabled '0'`) and Passwall enabled.

The first LuCI VM runs found a real ACL defect: `fs.exec` also needs
`ubus: { file: [ exec ] }`, not only per-command `file` entries; it was fixed
before run 6. Other failed runs were test-harness issues (kernel messages on
the serial console, a random password without a digit, the rpcd login
setup).

## Default LAN interface (daed 2.1.1-r2, luci-app-daed 1.0.0-r3)

On the router daed proxied only its own traffic: the dashboard's first-run
config had no `lan_interface`, so the log had `Bind to WAN: pppoe-wan` and no
`Bind to LAN`, and LAN flows appeared in `nf_conntrack` masqueraded straight
out of the WAN. The router was hot-fixed by hand: `/etc/daed/wing.db` was
backed up to `wing.db.bak-20261101212233`, `lan_interface: "br-lan"` was
added to the selected config (version 1 → 2) and daed was restarted, after
which the log shows `Bind to LAN: br-lan`. Patch 004 and the
`default_lan_interface` option (see [daed](daed.md#no-lan-interface-lan-traffic-goes-direct))
prevent it for new configs.

| Check | Result |
| --- | --- |
| dae-wing unit tests (`go test -run DefaultLan ./graphql/service/config/`) | Passed |
| Init script `default_lan_interface` handling under BusyBox ash (unset, empty, option, list) | `br-lan`, `br-lan`, value, space-joined list |
| `node scripts/tests/test-luci-daed-view.js` | Passed |
| `make package/custom/daed/compile`, `make package/custom/luci-app-daed/compile` | Passed; patch 004 applied |
| `zh_Hans` translation (`msgfmt -c --statistics`) | 30 translated messages |
| `scripts/tests/test-daed-vm.py` (new `default-lan-interface` and `luci-default-lan-interface` checks) | **Not run**; no image was built |

Router install, at the user's request and before publication: to keep daed
running, the two APKs were installed from a temporary repository whose index
was signed with the build key (`apk add --upgrade --scripts=no
--repositories-file /dev/null --repository /tmp/daed-r2/packages.adb daed
luci-app-daed`; a simulation first showed exactly these two upgrades). This
skips `default_postinst`, whose `/etc/init.d/daed start` would have restarted
daed because the procd instance gained an environment variable, and leaves
`/etc/apk/world` unpinned. The LuCI caches were cleared and rpcd reloaded by
hand. The router's modified `/etc/config/daed` was kept (the package default
went to `daed.apk-new`). The user then restarted daed: it runs the r2 binary
(SHA-256 `d557f5f7…dfca8`, identical to the build), with
`DAED_DEFAULT_LAN_INTERFACE=br-lan`, `Bind to LAN: br-lan` and two tcx links
on `br-lan`. daed is now enabled on the router.

Published afterwards with `scripts/publish-changed-feeds.sh` (dry run first):

| Check | Result |
| --- | --- |
| Changed packages | `daed`, `daed-geoip`, `daed-geosite` 2.1.1-r2, `luci-app-daed` 1.0.0-r3, `luci-i18n-daed-zh-cn` 26.305.50690~59c6c77 |
| Identity with the router install | `daed-2.1.1-r2.apk` `2ff2affe…ade5` and `luci-app-daed-1.0.0-r3.apk` `6dcdeb2a…f625` are the installed files; the preflight lists neither as a change |
| Router upgrade preflight | Passed; userspace simulation `full`/`passed`, no blockers |
| Userspace snapshot | `/srv/openwrt-feeds/public/snapshots/20261101T140703.769121Z` |
| Kernel | Unchanged (generation 45) |
| Receipt | `/srv/openwrt-feeds/upgrade-receipts/1793542073921869316.json` |

## Vision UDP DNS fix (daed 2.1.1-r3)

The router's daed log had 345 `DNS forward to upstream failed ...
error=short buffer network=udp+4` warnings for the `tcp+udp://8.8.8.8:53`
upstream reached through the VLESS `xtls-rprx-vision` node, and its
`udp4(DNS)` health flapped (10 × `ALIVE --udp4(DNS)-> NOT ALIVE` in the 25
minutes after a restart). Cause: `vision.PacketConn.ReadFrom` compared the
reply length with `uint16(len(p))`, which is 0 for dae's 65536-byte DNS
buffer. The upstream `daeuniverse/outbound` and `olicesx/outbound` main
branches have the same comparison.

| Check | Result |
| --- | --- |
| Reproduction against the pinned module (`go test` via the dae-core module graph, 120-byte reply) | Buffers of 512, 4096, 65535 bytes read it; 65536 and 131072 fail with `short buffer` |
| `go test github.com/daeuniverse/outbound/protocol/vless/...` with patch 005 | Passed, including the new `TestReadFromAcceptsBuffersOf64KiBAndMore` |
| `go test ./graphql/service/config/` (patch 004 tests) | Passed |
| `python3 scripts/tests/test-custom-package-updates.py` | Passed |
| Outbound source | Go proxy zip SHA-256 `c7ab45a9…204d`, the module version `go.sum` pins |
| `make package/custom/daed/compile` from clean | Passed; patches 001–005 applied; `go version -m` shows `github.com/daeuniverse/outbound => ./third_party/outbound` |
| `scripts/tests/test-daed-vm.py` | **Not run**; no image was built, and the VM test's SOCKS5 node does not exercise Vision |

The other warnings in that log (`tls: first record does not look like a TLS
handshake`, `unexpected EOF` on TCP DNS, and the SERVFAILs they cause) come
from the TCP path to the node and are not addressed by this release.

Router changes, at the user's request and without restarting daed:

- Workaround: the selected DNS row in `/etc/daed/wing.db` was changed from
  `googledns: 'tcp+udp://8.8.8.8:53'` to `'tcp://8.8.8.8:53'` (version 1 → 2,
  `pragma integrity_check` ok) after an online backup to
  `wing.db.bak-20261101222044`. It takes effect at the next daed restart.
- Published with `scripts/publish-changed-feeds.sh` (dry run first): `daed`,
  `daed-geoip`, `daed-geosite` 2.1.1-r3, snapshot
  `/srv/openwrt-feeds/public/snapshots/20261101T142514.285188Z`, receipt
  `/srv/openwrt-feeds/upgrade-receipts/1793543162396961351.json`, kernel
  unchanged, preflight passed with no blockers. The published
  `daed-2.1.1-r3.apk` is the built file (`23bf0a85…1140`).
- Installed from the feed with `apk add --upgrade --scripts=no daed
  daed-geoip daed-geosite` after a simulation listed exactly those three;
  `/etc/apk/world` unchanged, `/usr/bin/daed` matches the build
  (`984b2b40…b736`). daed kept running the r2 binary (pid 1684) until the
  user's restart.

## Vision splice handover (daed 2.1.1-r4)

Implements option A of the [kernel proxy design study](dae-kernel-proxy-study.md):
patches 006 (outbound library) and 007 (dae core). Validated on 2026-11-04 on
the build host and in disposable KVM guests.

| Artifact | SHA256 |
| --- | --- |
| `daed-2.1.1-r4.apk` (`make package/daed/clean package/daed/compile`, not published) | `c019217c16e7ef47e1008b705269180a2430161edf323d6a6ff51e3002ae94a5` |
| `/usr/bin/daed` in it (`build_dir/.../daed-2.1.1/daed`) | `7f631af6c9697f8804b9039e1fd254cf2c7c031b91cbeb7ce93f2e0f9c584fc3` |

| Check | Result |
| --- | --- |
| `make package/daed/clean package/daed/compile V=s` | Passed; patches 001–007 applied without fuzz; the patched sources are byte-identical to the tested tree |
| Vision unit tests (`go test github.com/daeuniverse/outbound/protocol/vless/vision`, also with `-race`) | Passed: no socket before the switch or after `commandPaddingEnd`; socket offered after it, for `*vision.PacketConn` only over TCP; unknown underlays refused; pending coalescer bytes flushed on handover |
| Coalescer flush regression (`TestDirectWriteReachesSocketWithoutRead`) | Fails without the patch (6 bytes left in the coalescer), passes with it |
| dae relay tests (`go test -race ./control/ -run 'Relay\|Splice\|Offload\|Gather\|Bufio\|Sniff\|Direct'`, then the whole `./control/` and `./component/sniffing/`) | Passed. The new tests relay 8 MiB over loopback with a provider that switches after one chunk (download and upload), a provider that never switches, and a sniffed prefix that must precede spliced bytes; byte-exact and fully recorded. With the handover disabled the three handover tests fail |
| `go test github.com/daeuniverse/outbound/protocol/vless/... pkg/coalesce netproxy` | Passed |
| End-to-end (scratch test, not shipped): xray-core 26.10.31 from this tree as a VLESS + REALITY + Vision server on loopback, outbound's `vless://` dialer (`*vision.PacketConn`, xudp default), dae's `RelayTCPContextWithRecords`, inner TLS 1.3 with 16 MiB up and 64 MiB down | Passed; SHA-256 of the upload and every download byte checked; Vision reported both directions direct; relay counters 16801457 up and 67200966 down |
| Same test under `strace -f`, test-only switch to disable the handover | dae's process (which also runs the inner client and target): copy loop 160.6 MiB `read` and 160.2 MiB `write`, no `splice`; handover 80.5 MiB `read`, 80.2 MiB `write` (the in-process endpoints) and 160.2 MiB through `splice`, i.e. the relay's copies moved entirely to splice |
| Throughput or CPU on the N5105 | **Not measured.** The loopback run is not a benchmark (both took about 5.2 s, bounded by the test's own byte checks and xray) |
| Image | `python3 scripts/build-and-publish.py build-only -j12 V=s` (kernel sequence 49, nothing published): `openwrt-x86-64-generic-squashfs-combined-efi.img.gz`, SHA-256 `9de2845ac62dcbed835668a9c29873814e1dfb385e2d29fbdf262c21c1b2dd84`; its manifest lists `daed - 2.1.1-r4` |
| `scripts/tests/test-daed-vm.py` on that exact image (KVM router + LAN client) | Passed: all 29 required checks true (kernel options, Passwall interlock, direct and proxied routing, DNS, flow offloading, `send_redirects`, stop cleanup, restart, LuCI ACL and toggles, and the same checks after booting into the `procd recovery` entry). Regression check only: its SOCKS5 node does not exercise Vision, so the handover itself is covered by the host tests above |

Published afterwards at the user's request with `scripts/publish-changed-feeds.sh`
(dry run first, preflight passed with no blockers): `daed`, `daed-geoip`,
`daed-geosite` 2.1.1-r4, snapshot
`/srv/openwrt-feeds/public/snapshots/20261104T032415.180507Z`, receipt
`/srv/openwrt-feeds/upgrade-receipts/1793762676725134723.json`, kernel
unchanged (sequence 49). Nothing was installed on the router and daed there
still runs its previous release until it is upgraded.

## Evidence

`/srv/openwrt-validation/daed-validation-20261101/`: the exact image,
`network/validation.json`, `daed-run{1..6}/validation.json` with per-guest
command and serial logs; the LuCI image and its runs are under `luci/`. The
default LAN interface build, dry-run and publication logs are under
`default-lan-20261101/`. The Vision UDP build and publication logs and the
pre-fix reproduction test are under `vision-udp-20261101/`. Build logs are in `logs/daed/` of the build tree.
The Vision splice handover build log, Go test output, the scratch end-to-end
test and its `strace` summaries are under `vision-splice-20261104/`.


## Additional upstream backports (daed 2.1.1-r8)

Validated on 2026-11-09 on the build host (Linux `7.2.15+deb14-amd64`,
Go 1.27). Patches 010–014 backport dae commits `17cc1de`, `2649d5b`,
`5a5473d`, `e6e52bb`, and `8722db0`; full commit links and behavior are in
[the feature guide](daed.md#upstream-version-and-backports). Existing
patches 001–009 are byte-for-byte unchanged. The new patches were refreshed
with `make package/custom/daed/refresh V=s`; the strict-alignment verifier
test is included in full because it did not exist in the v2.1.1 base.

| Check | Result |
| --- | --- |
| New patches applied through quilt with `--fuzz=0` | All five passed |
| `make package/custom/daed/clean V=s`, then `make package/custom/daed/compile -j3 V=s` | Passed; all 14 patches applied without fuzz; BPF objects regenerated for both endiannesses; all three r8 APKs built |
| `go test -race -count=1 -timeout=180s ./control ./component/daedns ./pkg/config_parser ./cmd github.com/daeuniverse/outbound/protocol/vless/...` from `dae-core` | All six packages passed, including existing Vision handover/audit coverage and the new splice, bootstrap, config, and namespace tests |
| Short-splice and bootstrap tests with a Go source overlay restoring the two old expressions | Both failed as expected: short reply timed out at 150 ms, bootstrap dialer inherited the requesting IP family; the shipped sources were not changed by the overlay |
| `TestProductionProgramsLoad` from a compiled control test binary under `sudo -n` | Passed all eight combinations of redirect-peer, current-task and strict-alignment switches; loads production BPF programs without attaching network hooks |
| `TestDeleteNamedNetnsKernelLockedMount`, verbose, unprivileged | Passed (not skipped), using nested user/mount/network namespaces and a private tmpfs `/run`; confirms recovery against a real locked namespace mount without covering the host's `/run/netns` |
| `python3 scripts/tests/test-custom-package-updates.py` | 47 tests passed |
| `node scripts/tests/test-luci-daed-view.js` | Passed |
| `python3 scripts/update-custom-packages.py --check --package daed` | `daed: local`, as intended for the composed recipe |
| `scripts/checkpatch.pl --no-tree --no-signoff` on patch 014 | Zero errors, one reviewed warning: the upstream volatile 16-bit load intentionally prevents clang fusing adjacent halfword loads into an unaligned 32-bit load. The upstream commit has no Signed-off-by trailer, so signoff checking was disabled; no trailer was invented |
| `git diff --check` | Passed |
| Existing `.config` SHA-256 before and after | Unchanged: `0b56e92e37cd76d8c7e75c38b0359b20ef77ab2710ce338b98cf9266abf6a7b5` |

| Artifact (`bin/systemd/packages/x86_64/base/`) | SHA-256 |
| --- | --- |
| `daed-2.1.1-r8.apk` | `64c76d4add3c96b4ceee0079b674250ba2513c8be507d8e60a989cfe8a01a314` |
| `daed-geoip-2.1.1-r8.apk` | `ebbe578121144b83be7d5fbd5cb33f1b56c853d455ba46c815bd68302a2ecc51` |
| `daed-geosite-2.1.1-r8.apk` | `eabb864694667fbccbf4771606575bf94cf4f3662d8194764fb2bf12831ecc3c` |

Build and test logs, upstream commit JSON and the baseline source overlay are
saved in `/srv/openwrt-validation/daed-validation-20261109/upstream-backports/`.
The overlay paths refer to the original scratch directory
`/tmp/daed-backport-20261109/`.

No image or VM boot was performed for r8, and no physical-router acceptance
was performed. No packages were published or installed on the router, and no
router configuration or service state was changed. Host BPF verifier and
isolated-namespace checks do not establish target-router acceptance.
