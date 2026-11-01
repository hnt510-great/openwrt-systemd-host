# Full cone NAT validation

Validated on 2026-11-01 on the build host. The packages and the kernel patches
were first built and tested in isolation, then published with
`scripts/build-and-publish.sh -j12` as kernel generation 43
(`7.3.1-owrt-2f47df105af5f7d3cac5e3b7f5fd2bee-r1-g43`). The user upgraded and
rebooted the router; the router checks below were made afterwards. No image
was built.

## Artifacts

| Artifact | SHA256 |
| --- | --- |
| `hack-7.3/982-netfilter-add-bcm-fullcone-masquerade.patch` | `fd7825f3493e5e7964dabbf88ac749db4d4b7f50680ec28553639f8785e4a1fc` |
| `hack-7.3/983-netfilter-nft_masq-add-fullcone-attribute.patch` | `2a297af1948d7f4409906c9a357373911d8fbb33c837ff78386282fd05f7de4a` |
| `libnftnl11-1.3.2-r4.apk` | `08ae6627d8d17c457b78e8243fea026764036ccdf8011d50ea34d488c4781467` |
| `nftables-json-1.1.7-r4.apk` | `4db422c4aef663437acdb2f57099925547562876ed53741b303a5284161c6e14` |
| `firewall4-2026.10.29~e6f600c4-r2.apk` | `7539df8e8a77c72721bf232ecb597a5638c08ee82adb8dc79c32948243df3cc6` |

## Source and build checks

| Check | Result |
| --- | --- |
| Full Linux 7.3.1 stack (`validate_patches()` from `update-mainline-kernel.py`, fuzz 0) | Pass; patched `nf_nat_masquerade.c` identical to the compiled source |
| `test-mainline-kernel-updates.py` with the new manifest entries | 20 tests pass |
| `checkpatch.pl` on 982 and 983 | 0 errors, 0 warnings, 0 checks |
| Compile of `nf_nat_masquerade.o`, `nft_masq.o`, `xt_MASQUERADE.o` with the fork's 7.3.1 config, plus `-Wextra` | No warnings |
| `make modules` (modpost) on a reflinked copy of the configured tree | Pass; all new imports resolve to `nf_conntrack` exports |
| libnftnl 001/002, nftables 100/103/104, firewall4 001/002/007/008 on pristine sources | All apply with fuzz 0 |
| `make package/{libnftnl,nftables,firewall4}/{clean,compile}` | Pass; no warnings in patched code |
| Release identities | `libnftnl`/`nftables` moved to `r4`: `r1`/`r2` map to the published `r3` in `configs/apk-elf-rebuilds.mk` |
| New `nft` against the host kernel: parse, list, JSON round trip | `masquerade fullcone` parses; netlink carries `[ masq fullcone 1 ]`; an unpatched kernel ignores it |

## Kernel behaviour (QEMU/KVM)

The suite ran twice: on Linux 7.3.1 with the fork's configuration plus
982/983 and `KASAN`, `PROVE_LOCKING`, `DEBUG_ATOMIC_SLEEP`, `DEBUG_LIST` and
`PANIC_ON_OOPS` (before the Kconfig symbol was added), and again on the
production configuration with `CONFIG_NF_NAT_MASQUERADE_FULLCONE=y` and the
final patch. Each kernel booted from an initramfs that carries the target rootfs tools and the new
nft/libnftnl. Two LAN namespaces sit behind the guest's root namespace, which
masquerades to a WAN namespace holding two remote addresses. UDP conntrack
timeouts were set to 4 s.

| Check | Result |
| --- | --- |
| A: plain `masquerade`, outbound | Pass (`10.0.0.1:5000`) |
| A: unsolicited packet from a host never contacted | Dropped (control) |
| B: rule lists as `masquerade fullcone` | Pass |
| B1: internal port preserved; expectation `PERMANENT BCM-NAT` installed | Pass |
| B2: unsolicited packet from a new remote host reaches the LAN host | Pass |
| B3: second destination from the same endpoint reuses the external port | Pass |
| B4: second LAN host on the same internal port | Pass; external port 5102 (different, same parity) |
| C: conntrack expiry | Pass; expectations removed, helper references released |
| D: `modprobe -r nft_masq` with live BCM-NAT mappings, then reload | Pass; full cone works after re-registration |
| E: `xt_MASQUERADE` loads with the address initialisation | Pass |
| `dmesg` | No BUG, WARNING, KASAN, lockdep, refcount or list-corruption reports |
| Production-configuration run | Same 24 checks pass (with the dnsmasq sections); no kernel warnings |

## Kernel ABI

`Kernel/Configure/Default` was replayed on the build host: `kconfig.pl` over
the generic, x86 and x86/64 configs, the `CONFIG_KERNEL_*` copy, the package
overrides from the current build tree and the initramfs edits.

| Check | Result |
| --- | --- |
| Replay with the committed `config-7.3` | Byte-identical to the build tree's `.config.set`; vermagic `2a97e7c5ca6a8af1585dd0410625ea73` matches `.vermagic` |
| Replay with the new `config-7.3` | Only difference `CONFIG_NF_NAT_MASQUERADE_FULLCONE=y`; vermagic `2f47df105af5f7d3cac5e3b7f5fd2bee` |
| `olddefconfig` on the new `.config.set` | `CONFIG_NF_NAT_MASQUERADE_FULLCONE=y`; no unset-symbol abort |
| `bzImage` + `modules` with the production configuration | Pass |
| Symbol disabled | `nf_nat_masquerade.o` compiles without warnings and contains no `bcm_nat` symbols |

## Publication

| Check | Result |
| --- | --- |
| `build-and-publish.sh -j12` | Exit 0; userspace and kernel generation 43 published |
| OpenWrt kernel build | `.config` has `CONFIG_NF_NAT_MASQUERADE_FULLCONE=y`; `kernel.release` `7.3.1-owrt-2f47df105af5f7d3cac5e3b7f5fd2bee-r1-g43`; `nf_nat_masquerade.o` contains the `bcm_nat` code |
| Router preflight (simulated against the installed `2a97e7c5…` system) | Passed, mode `full`: kernel ABI `2a97e7c5…` → `2f47df10…`, new `linux-image-…-g43` and kmods, `libnftnl11` r3 → r4, `nftables-json` r3 → r4, `dnsmasq-full` r9 → r10, `firewall4` r1 → r2, `luci-app-firewall` → `26.304.84321~51551b1` |

## Router (`192.0.2.1`, after upgrade)

| Check | Result |
| --- | --- |
| Running kernel | `7.3.1-owrt-2f47df105af5f7d3cac5e3b7f5fd2bee-r1-g43`; `kernelctl` state `phase: ready`, `known_good` g43, `previous_good` g42, no pending trial; `kernelctl check` exit 0 |
| Installed packages | `libnftnl11-1.3.2-r4`, `nftables-json-1.1.7-r4`, `firewall4-…-r2`, `luci-app-firewall-26.304.84321~51551b1`, `dnsmasq-full-2.93-r10` |
| Configuration | `firewall.@defaults[0].fullcone='2'` (set through LuCI) |
| Ruleset | `meta nfproto ipv4 masquerade fullcone comment "!fw4: Masquerade (Fullcone) IPv4 wan traffic"` |
| Live mappings | 56 `PERMANENT BCM-NAT` expectations on `192.0.2.81` (WAN, PPPoE behind carrier-grade NAT); `nf_conntrack_expect_max` 4096 |
| `dmesg` | No BUG, WARNING, refcount or list reports |
| STUN from LAN host `192.0.2.165`, port 40125, China-direct servers (miwifi, bilibili, hitv) | Router conntrack shows masquerade to `192.0.2.81:40125` (port preserved, `mark=0`, not proxied) and expectation `dport=40125 PERMANENT BCM-NAT`. Public mapping `203.0.113.10:31135` for all three servers (endpoint-independent mapping, including the ISP NAT) |
| RFC 5780 filtering (`stun.miwifi.com`) | Responses from a changed address and port (`198.51.100.3:3479`) and a changed port (`198.51.100.2:3479`) reached the LAN host through the BCM-NAT expectation: endpoint-independent filtering end to end (NAT1) |
| STUN through passwall (Google, Cloudflare and others) | Flows carry passwall's mark and are not masqueraded by the router; the mapping seen (`203.0.113.20:37644`) is the proxy's, so full cone does not apply to proxied UDP |

## firewall4

The new firewall4, nftables and libnftnl were overlaid on a reflinked copy of
the `root-x86-systemd` build root. `fw4 print` ran in an unprivileged
user/net/pid namespace, and every generated ruleset was checked with `nft -c`
against the host kernel.

| `fullcone` / `fullcone6` | Result |
| --- | --- |
| `0` / `0` (shipped default) | Plain IPv4/IPv6 masquerade; ruleset loads |
| `2` / `0` | `meta nfproto ipv4 masquerade fullcone`, "IPv4 brcm fullcone enabled for zone 'wan'"; loads |
| `2` / `1` | IPv6 probe fails, "disable IPv6 fullcone globally", IPv4 stays full cone; loads |
| `1` / `0` | Probe fails, "disable fullcone globally", plain masquerade; loads |
| `2` / `1` without patch 008 | Emits `meta nfproto ipv6 fullcone`; `nft -c` rejects the whole ruleset (the bug 008 fixes) |

## LuCI checkbox

| Check | Result |
| --- | --- |
| `node --check` on `zones.js` | Pass |
| `node scripts/tests/test-luci-firewall-fullcone.js` | Pass: one `Flag` `fullcone` in the `defaults` section after the policies, `enabled='2'`, `disabled='0'`, default unchecked (LuCI's `Flag` removes the option when cleared, `rmempty` is the default), no `fullcone6`, hidden without firewall4; fails against the unmodified view |
| `msgfmt -c` on the template and zh_Hans/zh_Hant catalogs | Pass (only pre-existing header warnings) |
| `make package/feeds/luci/luci-app-firewall/{clean,compile}` | Pass; payload `zones.js` contains the option and `firewall.zh-cn.lmo` the translation |
| Release identity | `feeds/luci` commit `51551b1c9c` gives `luci-app-firewall-26.304.84321~51551b1` and `luci-i18n-firewall-zh-cn-26.304.84321~51551b1` (published) |

Not checked: rendering and saving in a browser.

## Scope

Not checked: a complete image, a physical WAN or PPPoE link, real applications (games,
VoIP, BitTorrent), interaction with software or hardware flow offloading,
behaviour when `nf_conntrack_expect_max` is exhausted, and installation on the
router.

**Evidence:** `/srv/openwrt-validation/fullcone-nftset-validation-20261101/`
(`vm/` test script, initramfs builder and both console logs; `kernel/` debug
and production configurations and hashes; `abi/` replayed `.config.set` files
and vermagic; `fw4/` mode test and output; `router/stun_nat.py` STUN probe;
`build-logs/`, including `build-and-publish-20261101-fullcone.log`).
