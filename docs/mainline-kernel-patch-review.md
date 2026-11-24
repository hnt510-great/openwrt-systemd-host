# Review of the 6.18 patch stack against Linux 7.3

Initial review completed 2026-10-24. Its 481 source patches and all existing
ported-patch hashes matched the generation-30 baseline. No incoming source-patch
changes were found at that point. The review found three concrete optional-feature
problems; the complete 6.18 stack is not a drop-in Linux 7.3 patch stack.

All three affected options are disabled in the validated generation-30 kernel.
The initial review changed the audit metadata and documentation, not kernel
patches, signed APKs, published snapshots, or router state. The later source
synchronization is recorded at the end of this report.

## Findings

### P2: MAP-E/IPv6 tunnel port fails compilation when enabled

`pending-7.3/666-Add-support-for-MAP-E-FMRs-mesh-mode.patch` changes `HASH()`
from two arguments to one. Linux 7.3 has two additional wildcard-address lookup
calls that the port leaves as `HASH(&any, local)` and `HASH(remote, &any)`.
Both calls are in the final prepared `net/ipv6/ip6_tunnel.c`.

A targeted compilation of that actual source against an isolated copy of the
packaged generation-30 SDK fails at lines 155 and 168 with
`too many arguments to function 'HASH'`. The helper is defined at line 77.
The normal x86 build did not compile this file because
`CONFIG_IPV6_TUNNEL` is unset.

The lookup/bucket logic needs rebasing for Linux 7.3's separate wildcard paths;
updating only the helper declaration is insufficient. Validate both wildcard
cases and MAP-E matching when fixing the port. Native IPv6 networking does not
require this optional tunnel driver and is unaffected by this finding.

### P2: Quectel RM500Q-AE PCI binding was incorrectly omitted

`backport-6.18/935-v7.3-bus-mhi-host-pci_generic-Add-Quectel-RM500Q-AE-support.patch`
was classified as upstream from its filename's version prefix. The v7.3 tree
does not contain its subsystem binding for vendor/device `17cb:0306`, subsystem
`17cb:5002`.

The carried `pending-7.3/936-...` patch creates the dedicated
`mhi_quectel_rm500q_info` configuration, but the final PCI table has no
`driver_data` reference to it. That identifier occurs only in its definition.
The modem would therefore match the generic SDX55 entry instead of the intended
Quectel configuration. The original patch explains that the generic QMI channel
layout does not work with this firmware's MBIM interface.

The audit now marks patch 935 `needs-port`. Restore the specific PCI binding
while reconciling the 935/936 series to avoid duplicate configuration structures.
`CONFIG_MHI_BUS_PCI_GENERIC` is unset in generation 30.

**Resolved 2026-11-02.** Upstream commit `f6985f512f82` is in Linus's tree
after v7.3, so it is now `backport-7.3/935-v7.4-*`, and `pending-7.3/936-*`
is rebased on it in its original form. See the 2026-11-02 section below.

### P2: DMA-BUF heap drivers are omitted by an inherited Makefile change

`hack-7.3/904-debloat_dma_buf.patch` rewrites the heap directory's rules from
`obj-$(CONFIG_DMABUF_HEAPS_SYSTEM/CMA)` to `dma-buf-objs-$(...)`. That directory
does not define a composite target consuming those variables. Its parent still
descends into `heaps/` as an ordinary Kbuild directory.

Using the actual Linux 7.3 `scripts/Makefile.build`, with both heap options
enabled, produces an empty `heaps/built-in.a` command. An isolated control using
the upstream `obj-*` rules schedules both `system_heap.o` and `cma_heap.o`.
This defect is inherited from the 6.18 patch; it was not introduced solely by
the 7.3 rebase.

Keep the heap objects in that directory's normal `obj-*` lists and validate
their enabled configuration. `CONFIG_DMABUF_HEAPS` is unset in generation 30;
the enabled DMA-BUF core and sync-file support are separate from these heaps.

**Resolved.** See the DMA-BUF heap resolution section later in this report and
`configs/mainline-kernel-patches.json`.

## Patch accounting and provenance

The corrected disposition of the 481 source patches is:

| Disposition | Count |
| --- | ---: |
| Already upstream or equivalent in 7.3 | 192 |
| Carried through patch refresh | 251 |
| Carried through manual merging/rebasing | 35 |
| Superseded by upstream changes | 2 |
| Omitted binding requiring a port | 1 |

The 286 carried patches include the optional-feature findings above. The
additional nfnetlink compatibility patch makes 287 currently applied patches.
All 287 were reapplied to the verified Linux 7.3 source archive with zero fuzz
during this review. Application success does not establish correctness for
every configuration, as the targeted tunnel compile demonstrates.

Upstream history was checked against the canonical v7.3 tag, whose annotated
tag object is `091b06388b117fefdcb63336ac09956a4914b961` and release commit is
`c03c1a14507dfaf8b856c2608f9ac216021fc222`. Kernel.org and the maintainer's GitHub
repository advertised the same tag. A filtered history fetch supplied 95,809
ancestor commits from the selected date range.

For the original 193 upstream classifications:

- 151 patch-header commit IDs were present in that ancestry.
- Another 39 had corresponding upstream commit subjects. Their primary-source
  commit patches were fetched: 30 have identical added/deleted lines; the other
  nine differ through LTS API adaptations, protocol numbering, whitespace,
  maintainer entries, or drivers omitted from the older branch. Those differences
  were inspected rather than treating the patch filename as proof.
- The ath12k binding cleanup and netfilter dependency cleanup pass exact
  zero-fuzz reverse-application checks against the prepared 7.3 source.
- Quectel patch 935 lacked the required binding and is the corrected exception.

The two superseded omissions remain justified. Patch 699's output-interface
fallback addresses the older forward-path API; 7.3 refuses offload when discovery
fails and explicitly assigns the successful path's output interface. Patch 812's
PCI race involved `pci_sysfs_init()` and `pci_create_sysfs_dev_files()`, neither
of which remains in 7.3's PCI sysfs implementation.

The previously corrected bridge BPDU netlink bound, flowtable destination
validation adaptation, standalone nfnetlink module, kallsyms changes, and r8169
LED naming were also inspected. No additional defect was identified in those
paths by this review. The existing full build and VM receipts remain evidence
for the selected x86 configuration, not every optional driver or architecture.

## Evidence and limits

Private review evidence is retained at
`/srv/openwrt-validation/openwrt-mainline-20261024-084724/patch-review-20261024T063814Z/`.
It includes the complete inventory, upstream ancestry and change comparisons,
the isolated SDK compile failure, the actual Kbuild dry-run/control logs, the
missing PCI-reference check, and the repeated zero-fuzz result.

The audit registry links each finding to its source patch. The kernel patch
files and generation-30 artifact hashes remain unchanged. These findings need
fixes and configuration-specific tests before those optional features are
advertised as supported. No physical hardware test, installation, publication,
or reboot was performed as part of this review.

## Upstream synchronization after generation 30, 2026-10-24

Merged OpenWrt through `6db25ee835`, including 15 incoming commits since the
previous main-tree merge. Compared the complete incoming file list and every
generic/x86 6.18 patch against the audit registry, rather than inferring
inclusion from patch filenames.

Commit `818516b92c` adds
`generic/pending-6.18/344-MIPS-lib-use-maddu-and-prefetch-in-csum_partial.patch`
and removes the older Realtek-specific checksum patch that it replaces. Linux
7.3 does not contain the new checksum loop. The patch applies unchanged, with
zero fuzz or offsets, to the verified Linux 7.3 archive. It is now carried in
`generic/pending-7.3/` with identical source/ported SHA256 values in the registry.
It changes MIPS assembly only and does not change x86 checksum code.

The incoming mvebu Wi-Fi PCIe reset patches and Realtek PCS source changes
remain in their board-specific 6.18 trees. Those boards still select 6.18;
the local 7.3 port selects only x86/64, so copying those board-specific files
into the x86 patch stack would not be appropriate. No other generic or x86
6.18 patch was added, modified, or removed by this synchronization.

The registry now accounts for all 482 generic/x86 6.18 source patches, with
no missing entries or stale source/ported hashes. The additional carried MIPS
patch raises the full applied 7.3 stack from 287 to 288 patches. All 288 apply
with zero fuzz to the verified Linux 7.3 archive plus the current source
overlays. Existing generation-30 patch files remain unchanged.

Checkpatch reports the new patch's inherited `Assisted-by: LLM` trailer as
nonstandard and lacking an email address. The carried copy preserves upstream
provenance byte for byte; the diagnostic concerns that trailer.

The packages and video feed merges preserve the local native-systemd,
rootless-storage, desktop, and audio changes while adopting upstream updates.
Podman's new `install.bin` build target does not install systemd units, so
the merged recipe also invokes `install.systemd` for native-systemd builds.
The verified Podman 6.1.2 source accepts the existing rootless-overlay patch
with zero fuzz, and its real `install.systemd` target stages all unit files
referenced by the recipe in an isolated destination. Mesa now uses upstream's
packaged host Python build dependencies instead of a private pip requirements
file; the local media configuration remains intact.

Strict `conf --fatalrecursive` initially caught a cycle after upstream switched
fwknop to `gnupg2-utils`. That package's plain `gnupg2` dependency propagated
through `luci-app-fwknopd` and its package-controlled `FWKNOPD_GPG` option.
Selecting the required runtime with `+gnupg2` removes that cycle. The strict
check now passes against the regenerated package metadata, writing its result
to an isolated file and preserving the working `.config`.

All nine feed indexes are nonempty, with no broken generated package links.
Removed only the stale generated `gnupg` and `vnstat` links after upstream
removed those recipes. The mainline updater, kernel-input, metadata/Kconfig,
Podman native-storage, desktop-audio, LuCI Podman, and LuCI QEMU Python suites
pass all 55 tests; both LuCI JavaScript view checks also pass. Preservation
checks cover 65 pre-existing files, stashes in all 12 repositories, retained
local commit ancestry, and unchanged unrelated nested checkout heads/status.
The custom updater advanced libostree from 2026.4 to 2026.5; that recipe change
is left uncommitted for review.

Package scanning still reports missing-dependency warnings for bmx7 packages,
`kmod-echo`, and the existing `libubus`/`json-c` build-dependency names. Incoming
packages-feed patch files also retain upstream whitespace diagnostics; the
locally resolved recipe changes pass their focused whitespace checks.

This synchronization validates source integration and patch application.
It does not rebuild firmware or APKs, prove MIPS execution, or replace the
generation-30 VM and hardware evidence. The three optional-feature findings
above remain open. No feed publication, physical installation, or reboot is
part of this synchronization.

## Upstream synchronization review, 2026-10-26

Reviewed the 14 incoming main-tree commits through `6c9452a35b`, merged as
`45abcc3128`. The only generic/x86 patch-stack change is OpenWrt commit
`2d7e2a4ae6574279e3c2c60b28785fcf692ff2ba` (flowtable forward-path fix).
The review found one downstream change requiring a Linux 7.3 port:

- **Port the updated `hack-6.18/650-netfilter-add-xt_FLOWOFFLOAD-target.patch`
  behavior into `hack-7.3/650-netfilter-add-xt_FLOWOFFLOAD-target.patch`.**
  The current 7.3 patch still declares `nf_dev_path_info()` and
  `nf_dev_forward_path()` as `void`, ignores forward-path discovery failures,
  and falls back to the destination device's interface index. The incoming
  change propagates errors, releases both route destinations on failure,
  validates bridge encapsulation counts, and adds `DEV_PATH_IEEE80211` /
  `.ieee80211 = true` handling. These changes are absent from the local port.
  Upstream explains that retaining failed-path offload can emit packets with
  a zero destination MAC and flood bridge ports. The inspected existing
  build configuration has `CONFIG_NETFILTER_XT_TARGET_FLOWOFFLOAD` unset;
  this is an optional-feature port requirement, not a reproduced runtime
  failure of the currently enabled nftables path.
- The new `backport-6.18/706-03-v7.2-netfilter-flowtable-bail-out-if-forward-path-cannot-b.patch`
  carries upstream `871df5007eda`. Its nftables error-propagation behavior
  already exists in Linux 7.3: failed discovery returns `-ENOENT`, and the
  caller releases both destinations. Checked the pristine cached Linux 7.3
  source and the existing prepared source. Do not duplicate that backport.
- Deleted `pending-6.18/699-...` was already classified as superseded by
  `871df5007eda` in the 7.3 registry. It does not need a replacement port.
- The `pending-6.18/708-...` changes only refresh context and hunk locations
  against the new `int` function signatures. Its carried 7.3 behavior does
  not need another code change from this synchronization.
- The layerscape patch refresh and ath79, mpc85xx and Realtek changes are
  board-specific. Those targets retain their existing kernel series and
  do not belong in the x86/64 7.3 stack.

This was a check-only review of the 7.3 patches. No carried patch was changed.
The registry still describes the previous source snapshot: one source entry
was removed upstream (699), one added (706-03), and two source hashes changed
(650 and 708). Reconcile that provenance together with the 650 port; the
registry must not be treated as a hash-current audit of this new merge.
All existing registered ported-patch hashes still match.

Evidence is in `.git/pull-preserve/20261026T012820Z/`, including
`kernel-patch-audit.json`, pristine source excerpts and the release check.
The explicit release checker reports current/latest `7.3`. This review did
not build, publish, install or reboot a kernel. The three earlier optional
feature findings remain recorded above.

### FLOWOFFLOAD port completed, 2026-10-26

The follow-up port resolves the new 650 finding above. The 7.3 patch now
propagates forward-path/parser failures to the route caller, releases both
route destinations on failure, validates bridge encapsulation counts, and
handles IEEE80211 paths. Its target implementation matches the updated 6.18
implementation, with an additional explicit `linux/netfilter/x_tables.h`
include required to compile against Linux 7.3's headers. The optional target
remains disabled in the working kernel configuration.

The registry is reconciled with the merged 6.18 source stack: 706-03 is
classified as already upstream, the removed 699 entry is dropped, the 708
source hash is refreshed, and both 650 hashes reflect the port. All 482
current generic/x86 source patches are represented, with no missing/stale
entries or mismatched source/ported hashes.

Validation evidence is retained in `.git/kernel-port-20261026/`:

- The source archive SHA256 matches the recorded Linux 7.3 hash. All 288
  carried patches apply to a fresh extraction plus overlays with zero fuzz.
- The actual ported `net/netfilter/xt_FLOWOFFLOAD.c` compiles with
  `CONFIG_NETFILTER_XT_TARGET_FLOWOFFLOAD=m` in an isolated copy of the
  existing 7.3 build, using the OpenWrt GCC 14.4.0 toolchain.
- An isolated external-module build of the same source links
  `xt_FLOWOFFLOAD.ko` with successful modpost dependency resolution using
  the existing full kernel's `Module.symvers`. This is compilation/link
  evidence, not a replacement full firmware/package build or runtime test.
- The 20 mainline updater tests and 7 kernel build-input tests pass.
- `git diff --check` passes. Checkpatch retains inherited declaration
  indentation errors and style warnings from the existing patch; no new
  error category is introduced by this port. Modpost reports the inherited
  missing `MODULE_DESCRIPTION()` warning.

The original `.config`, prepared kernel build, image/module packages and
unrelated local edits are preserved. No publication, installation, VM test,
physical-device test or reboot was performed. The three earlier optional
feature findings are independent of this change and remain open.

### Incoming merge review, 2026-10-26 (`1702bf52fc`)

This review compares the latest merge with its first parent (`cddf35c0bd`).
The selected target remains x86/64 on Linux 7.3. The current 6.18 generic/x86
stack contains 488 patches; the registry still covers the preceding 482.
There are six unregistered additions and five changed source hashes, with no
removed entries. All registered 7.3 ported-patch hashes still match.

The new changes are **not fully carried into 7.3**. The following work is
needed to bring the maintained 7.3 stack in line with the merge:

| Source patch/change | Finding and required action | Current x86 build relevance |
| --- | --- | --- |
| `706-04-v7.3-netfilter-flowtable-use-the-vlan-id-not-the-full-tci.patch` | Port both VLAN tuple-key masks. Despite the filename, the verified 7.3 archive and prepared source still use `skb_vlan_tag_get(skb)` and unmasked `ntohs(veth->h_vlan_TCI)`. Nonzero PCP bits can prevent flowtable lookup from matching the programmed VID. | Flowtable support is enabled as modules. Relevant when VLAN traffic carries priority bits. |
| Existing `708-netfilter-flowtable-tear-down-direct-xmit-flows-when.patch` | Carry the new `info->port_vlans = 0` on each bridge path into `net/netfilter/nf_flow_table_path.c`. The existing 7.3 port sets `bridge_path` without clearing this counter. A later bridge in the path must start its own VLAN-layer count so FDB checks resolve the intended port. | Relevant to bridge paths, especially paths traversing multiple bridges/VLAN layers. Bridge and VLAN filtering are enabled. |
| `708-netfilter-flowtable-carry-a-priority-into-the-offload.patch` | Port the flow priority field, nftables capture, software forwarding behavior and hardware action. The similarly named existing `nf_flowtable.priority` is the control-plane hook priority, not this missing `flow_offload.priority`. | Relevant to `meta priority set` before `flow add`, and IPv4 forwarding's per-packet TOS priority behavior. |
| `709-netfilter-flowtable-advertise-the-vlan-match-in-used_keys.patch` | Carry the VLAN/CVLAN `used_keys` bits. The 7.3 `NF_FLOW_DISSECTOR` macro only sets offsets; the current match code does not advertise these VLAN keys. | Hardware flow offload correctness; mlx5 is one affected consumer. |
| `708-00-net-mlx5e-ignore-FLOW_ACTION_PRIORITY-on-flowtable-offload.patch` | Carry with the priority series to avoid rejecting formerly accepted mlx5 flowtable rules. The action handler is absent in 7.3. | `CONFIG_MLX5_CORE` is disabled in the current kernel; needed for completeness when that driver is enabled. |
| `642-net-bridge-switchdev-add-br_switchdev_fdb_find_port.patch` and `643-net-dsa-fix-host-fdb-refcount-when-a-bridge-fdb-entry-roams.patch` | Carry together. The switchdev lookup helper and per-port DSA host-FDB records are absent. The series avoids undercounting/leaking host-FDB references when bridge entries roam and notifications race. | `CONFIG_NET_DSA` is disabled. Not required by this x86 kernel's enabled drivers, but needed for 7.3 parity with the generic stack. |

Four changed existing patches contain no new added/deleted code: 650,
736-04, 795-01 and 795-03 only have hunk-line changes. They need source-hash
provenance refresh, not another functional port. The previous 650 forward-path
port remains intact. The fifth changed patch is the 708 bridge-path fix above;
its other changes are attribution/context updates.

Architecture-specific Airoha, ath79, Kirkwood, Octeon, Qualcomm, ramips and
Realtek changes in this merge are outside the selected generic/x86 stack.
They should not be copied into the x86/64 patch set merely to match upstream.

Review evidence:

- `.git/kernel-review-20261026T143649Z/audit.json` records the source/ported
  hash audit, changed-patch code comparison and forward/reverse dry runs.
- The Linux 7.3 archive was rehashed to
  `87363c24f10e06321eb362765521094e94471f6bff8bce2d6b3e40f39f004953`.
  Affected pristine files were extracted from that archive. Prepared-source
  inspection uses the retained zero-fuzz 288-patch validation tree from the
  earlier FLOWOFFLOAD port; all corresponding registered patch hashes match.
- Five of the six new patches pass forward dry runs against both pristine
  and prepared source with zero fuzz (line offsets are allowed), and fail
  forced reverse dry runs. The VLAN-ID patch needs a context refresh because
  the 7.3 function has additional local declarations. Both old expressions
  are visibly present in its source; neither failed dry-run direction alone
  is used as proof of upstream inclusion or omission.
- `CONFIG_NFT_FLOW_OFFLOAD=m`, `CONFIG_NF_FLOW_TABLE=m`, `CONFIG_BRIDGE=y`,
  `CONFIG_BRIDGE_VLAN_FILTERING=y`, `CONFIG_NET_SWITCHDEV=y`, with DSA and
  mlx5 disabled, were read from the existing prepared kernel configuration.

The earlier optional MAP-E, RM500Q-AE binding and DMA-BUF heap findings remain
open: the prepared source still contains the two-argument wildcard `HASH()`
calls, an unreferenced `mhi_quectel_rm500q_info`, and unconsumed
`dma-buf-objs-*` heap rules, respectively.

This is a check-only review. Kernel patches and the registry were not changed;
the registry remains stale for the incoming merge and must be reconciled with
the actual ports. Dry-run application is not compile/runtime validation. No
kernel build, VM test, publication, deployment or reboot was performed.

### Incoming fixes ported to 7.3, 2026-10-26

The follow-up implements all six additions and the existing bridge-path
correction listed above:

- The VLAN tuple-key fix is carried in `backport-7.3/706-04-...`, with its
  context refreshed for the additional 7.3 tunnel/parser declarations.
- Pending patches 642/643 carry the bridge switchdev lookup and DSA host-FDB
  synchronization together.
- Pending patches 708-00 and `708-...carry-a-priority...` carry mlx5 acceptance
  and the complete flowtable priority handling together, including the driver
  action cases for Airoha and MediaTek.
- The existing `708-...tear-down-direct-xmit...` clears `port_vlans` on each
  bridge path in the 7.3 `nf_flow_table_path.c`. Its attribution was also
  synchronized with the corrected incoming source patch header.
- Pending patch 709 advertises the VLAN and CVLAN dissector keys.

`configs/mainline-kernel-patches.json` now represents all 488 generic/x86
6.18 source patches. The six new ports are registered, the five changed source
hashes are refreshed, and the modified bridge-path port hash is updated.
There are no missing/stale source entries or source/ported hash mismatches.
The earlier table's missing-port findings and stale-registry warning are
resolved by this follow-up; the three earlier optional-feature findings remain
open and were not changed by this batch.

Validation evidence: `.git/kernel-backport-20261026T144039Z/`.

- A fresh extraction of the hash-verified Linux 7.3 archive plus the target
  overlays accepts all 294 carried patches with zero fuzz.
- Eleven affected objects compile with the OpenWrt GCC 14.4.0 toolchain in an
  isolated copy of the existing SDK: `nf_flow_table_core`, `nf_flow_table_ip`,
  `nf_flow_table_offload`, `nf_flow_table_path`, `nft_flow_offload`,
  `xt_FLOWOFFLOAD`, bridge `br_switchdev`, DSA `port`/`user`, and mlx5 TC action
  `act`/`skbedit_prio`. DSA, mlx5 Ethernet/eswitch/TC and its required
  `NET_TC_SKB_EXT` configuration are explicitly enabled for that compilation.
  The copied source files match the freshly validated patch tree.
- The 20 mainline updater tests and 7 kernel build-input tests pass.
- Checkpatch reports zero errors for all seven affected patches. The only
  warnings are its inability to resolve the two inherited Linux `Fixes:`
  commit IDs in this OpenWrt Git checkout. `git diff --check` passes.

The original `.config`, prepared kernel build and unrelated local edits are
preserved. This validates patch application and focused compilation, not a
full kernel/module link, firmware/package build or runtime behavior. No VM or
physical-device test, publication, installation, reboot, commit or push was
performed for this batch.


## Upstream additions reviewed, 2026-10-29

Merged OpenWrt through `795f369b181cd128962fa8f60a03eaf0ac8afac6`
(152 incoming main-tree commits). The selected target remains x86/64,
Linux 7.3, glibc and native systemd. The source review compares the incoming
changes, existing registry, hash-verified 7.3 archive and prepared source.

There are **23 new generic 6.18 source patches**. The complete generic/x86
6.18 inventory now contains 511 patches, while the unchanged registry still
contains 488. All 488 existing source entries and their registered ported
hashes match; there are no removed entries. The 23 additions need disposition
and registry entries when their ports are implemented. This review does not
classify a patch as already upstream from its filename or version prefix.

| New series | Count | Linux 7.3 finding | Current x86 configuration |
| --- | ---: | --- | --- |
| `835-01` through `835-05`, netdev LED trigger | 5 | Worth porting together; fixes reference leakage, worker UAF, sysfs group races, invalid interval handling and concurrent stores | `CONFIG_LEDS_TRIGGER_NETDEV=y` |
| `860-01` through `860-06`, AZ6007/DRXK/DVB core | 6 | Complete series applies to prepared 7.3 with zero fuzz; USB disconnect/error handling and release wakeups are absent | `CONFIG_DVB_CORE` disabled; media core alone is enabled |
| `753`, ZYXEL PMG3000-D20B SFP quirk | 1 | Forward zero-fuzz dry run passes and forced reverse fails; optional module-specific fix | `CONFIG_SFP` disabled |
| `735`, `793-01` through `793-04`, `794`, `797-00` through `797-02`, `798`, `799`, MediaTek/WED | 11 | Complete ordered series applies to prepared 7.3 with zero fuzz; platform fixes and wireless flow-priority/idle reporting integration | MediaTek SoC/WED not selected |

### Priority: netdev LED trigger

The five LED patches address code compiled into the current kernel and are the
first porting candidates. Prepared 7.3 still lacks the error-path `dev_put()`,
worker locking, `attr_lock` and shared software-blink predicate. Its interval
store silently accepts invalid values, and attribute stores still modify state
without the trigger mutex. Forced reverse dry runs do not find the new series.

Patches 01, 02 and 04 apply in an ordered trial with zero fuzz. Patches 03 and
05 each leave one context hunk unresolved in that trial. Linux 7.3 additionally
supports 25/40/50/100-Gbit link modes: patch 03's visibility-loop locking and
patch 05's conflicting-mode rejection must retain all those modes when rebased.
Do not drop the high-speed cases to make the 6.18 patch apply. Carry the worker
locking, asynchronous cancellation, hardware-control check and carrier check
as a coordinated series, then compile and exercise concurrent trigger/sysfs
updates and device removal. Application checks alone do not validate races.

### Other candidates and scope

All six DVB patches apply in sequence to copies of the actual prepared source
with zero fuzz; offsets occur. Patch 04 depends on patch 03's disconnect error
handling. These are useful optional-device candidates, but the selected kernel
does not build DVB core or those tuner drivers.

The eleven MediaTek patches also apply together with zero fuzz. In isolation,
`797-02` fails because it depends on the earlier series; its ordered application
succeeds. The DMA-unmap size fix `735-v7.3-...` is **not** present in the verified
7.3 release: pristine and prepared `mtk_wed_wo_dequeue()` still unmap using
`SKB_WITH_OVERHEAD(q->buf_size)`. Its filename is not proof of inclusion.
The flow-query additions depend on the matching wireless/backports driver
changes, so their integration needs platform-specific build/runtime validation.

Incoming BCM, Octeon, Qualcomm and Realtek board patches belong to targets
still selecting their own kernel series. Incoming mac80211 patches are merged
in the separate backports package; they are not automatically additions to the
native generic/x86 7.3 patch stack.

### Evidence and limits

Evidence is retained under
`.git/pull-preserve/20261029T002206Z/kernel-audit/`: incoming commit/file lists,
individual forced-reverse and forward dry runs, ordered-series trials, source
hashes and archive provenance. The 7.3 archive SHA256 is
`87363c24f10e06321eb362765521094e94471f6bff8bce2d6b3e40f39f004953`.
All 18 affected prepared source files match the retained, previously validated
294-patch tree byte for byte. Patch trials used isolated copies, preserving the
normal prepared build tree.

This is a review, with no new 7.3 patch or registry edit and no kernel build,
package publication, device deployment or reboot. The earlier MAP-E,
RM500Q-AE binding and DMA-BUF heap optional-feature findings remain open.
Strict Kconfig checking still reports the pre-existing native-libudev provider
recursion, also recorded before this synchronization in the GNOME deployment
logs; this update does not establish a passing strict Kconfig or full image.


### The 23 additions ported to Linux 7.3, 2026-10-29

The follow-up implements all candidates listed above: five netdev LED fixes,
six DVB hot-unplug fixes, the ZYXEL SFP quirk and eleven MediaTek/WED patches.
Twenty-one patches retain the upstream 6.18 bytes exactly. LED patches 03
and 05 are rebased for 7.3 while retaining the 25/40/50/100-Gbit visibility
and conflicting-mode checks. Worker locking, asynchronous cancellation,
carrier/offload gating and sysfs-group serialization are carried together.

The audit registry now covers all **511 generic/x86 6.18 source patches**,
with no missing/stale entries or source/ported hash mismatches. Existing 488
entries and existing 7.3 patches are unchanged. The earlier 23-entry registry
gap and LED-context failures are resolved. The older MAP-E, RM500Q-AE binding
and DMA-BUF heap findings remain outside this batch and remain open.

Evidence is under `.git/kernel-backport-20261029T003545Z/`:

- A fresh extraction of the SHA256-verified 7.3 archive plus the target
  overlays accepts all **317 patches with zero fuzz**.
- Eleven affected C objects compile with OpenWrt GCC 14.4.0 in an independent
  SDK copy: netdev LED, AZ6007, DRXK, DVB demux and CA, SFP, MediaTek Ethernet,
  PPE, PPE offload, WED and WED WO. COMPILE_TEST, MediaTek SoC/WED, CFG80211,
  DVB core/USB/AZ6007/DRXK and SFP are explicitly enabled in that copy.
  All 18 affected source/header files match the freshly patched tree.
- Twenty mainline-updater and seven kernel-input tests pass.
- Checkpatch has no new diagnostics relative to the source patches. The
  inherited three complex-macro-parenthesis errors in MediaTek patches 797-01
  and 797-02 remain, as do upstream Fixes-reference, nominal-author/signature
  and style warnings. The LED rebase introduces no checkpatch errors.
  `git diff --check` passes for the working changes; new patch payloads were
  checked separately.

The original `.config`, normal prepared kernel tree, feed repositories,
stashes and unrelated work are preserved. The optional configurations above
exist only in the disposable SDK copy. This is patch-application and focused
object-compilation validation; it is not a full kernel/module link, firmware
build, race stress test, ARM/MediaTek device test or physical deployment.
No publication, installation, reboot, commit or Git push was performed.


### Main/feed synchronization and new-patch review, 2026-10-29 (15:53 UTC)

Merged nine new main-tree commits through `ca454c00b6` into local merge
`7317e18d12`, retaining the working-tree changes and Linux 7.3 selection.
The incoming changes contain no additions, modifications or removals in the
generic/x86 6.18 or 7.3 patch directories. The Realtek GPIO interrupt change
is in that target's device tree and does not belong to the x86/64 7.3 stack.
The netfilter change corrects module package ownership in
`package/kernel/linux/modules/netfilter.mk`; it is a packaging update and
requires no additional native-kernel patch.

The two new mt76 pending fixes restart `mac_work` after channel changes and
limit MT7612U SuperSpeed TX A-MSDUs. They are already carried by
`package/kernel/mt76/patches/100-*` and `101-*`, with package release 2.
Both apply in order with zero fuzz to the SHA256-verified package source
`0936617dc529ff9da0385221d3fa6de732231177`. This driver is built from its
separate OpenWrt source package for the selected kernel; duplicating these
patches in the native 7.3 patch stack would target a different source tree.
All `kmod-mt76*` options are disabled in the preserved x86/64 configuration.
No mt76 module build or hardware test was performed.

All 511 source-patch registry entries and their recorded source/ported hashes
match the current files. A fresh extraction of the verified Linux 7.3 archive,
with the current target overlays, accepts all 317 patches with `--fuzz=0`.
The kernel updater (20), kernel input tracking (7), custom updater (43), and
APK source-version (2) tests pass. No new native 7.3 backport is required by
this incoming batch; the previously documented optional-feature findings are
unchanged.

Evidence: `.git/pull-preserve/20261029T155316Z/kernel-audit/`, including
`incoming-kernel-files.txt`, `registry-audit.json`, `mt76-audit.json`, and
individual mt76 application logs. This validation does not build or deploy a
new kernel, publish feeds, or reboot a device.

The completed feed run processes all 160 custom entries: PipeWire advances
from 1.6.10 to 1.6.11, 119 entries are current, 28 are locally maintained and
12 retain their configured maintenance branch pending review. PipeWire source
preparation verifies its SHA256 and applies both local patches. All nine feed
indexes are nonempty, generated package links have no broken targets, and
post-update strict Kconfig checking passes using a separate output file.
All 387 protected files, original index/stash state and 11 local repository
histories pass preservation checks. No original `.config` normalization was
performed. The snapshot includes `sync-summary.json` and the complete logs.

### Main/feed synchronization and new-patch review, 2026-10-30

Merged three main-tree commits through `5700101d7c` into local merge
`11f4a70bd0`, preserving the Linux 7.3 selection and local integration.
This incoming batch changes hostapd initialization, IPQ40xx board-data
selection and Realtek board network/LED defaults. It adds, modifies or removes
no generic/x86 kernel patch, kernel source overlay or external kernel-module
patch. The board-specific defaults do not require a native x86/64 backport.

All 511 generic/x86 6.18 source patches and all 317 carried 7.3 patches have
matching registry entries and SHA256 values. A fresh extraction of the
SHA256-verified Linux 7.3 archive, with the current target overlays, accepts
all 317 patches with `--fuzz=0`. No additional backport is required by this
batch. The three earlier optional-feature findings remain open.

Evidence is retained under `.git/pull-preserve/20261030T065000Z/`, including
per-repository incoming commit/file lists and `kernel-audit/registry-audit.json`.
This is source integration and patch-application validation; it does not
build firmware, publish packages, deploy to a device or prove runtime behavior.

The packages, LuCI and Passwall LuCI feed merges incorporate 11, one and one
incoming commits respectively. The OpenSSH release conflict retains local
`PKG_RELEASE:=3` and `CONFIG_OPENWRT_SYSTEMD` tracking, while adding upstream's
`openssh-server-pam` conflict with `openssh-server`. Its other local recipe
changes remain intact.

The custom updater checks all 161 entries successfully: 128 are current,
28 are locally maintained and five retain their configured maintenance branch
pending review. No recipe version changes are available within those policies.
All nine feed indexes are nonempty, generated package links have no broken
targets, and strict Kconfig checking passes using a separate output file.
The mainline-updater (20), kernel-input (7), custom-updater (43), package
metadata/Kconfig (4) and APK source-version (2) tests all pass. All 136 protected
files and all 11 repository histories, staged intent and stashes pass the final
preservation checks. The working `.config` is unchanged. The complete final
receipt is `verification-final.json` in the snapshot directory.

### Main/feed synchronization and new-patch review, 2026-10-31

Merged 31 main-tree commits through `a516fe3151` into local merge
`753820aaa7`, preserving the Linux 7.3 selection and local integration.
The only conflict was the PPP release: upstream advanced it to 5 for quoting
`REQPREFIX`/`IP6TABLE`, which merges cleanly with the local ujail changes.
Because the local release was already 6, the merged recipe uses
`PKG_RELEASE:=7` rather than reusing an existing identity.

This batch adds build-system Rust support and two generic 6.18 patches:

- `pending-6.18/803-rust-opp-pass-old-opp-to-config_clks.patch` adds the
  old-OPP argument to the Rust `config_clks` trampoline. Linux 7.3
  `rust/kernel/opp.rs` still has the old signature, while the carried
  `pending-7.3/802-OPP-Provide-old-opp-to-config_clks-on-_set_opp.patch`
  changes `config_clks_t` in the same way as 6.18. **Required for 7.3** when
  `CONFIG_RUST` and `CONFIG_PM_OPP` are enabled.
- `hack-6.18/791-net-phy-ax88796b-build-the-Rust-driver-next-to-the-C.patch`
  builds the Rust ax88796b PHY driver as a separate module for the new
  `kmod-phy-ax88796b-rust`. Linux 7.3 still replaces the C driver with the
  Rust driver. **Required for 7.3** for that package.

Both are carried unchanged as `pending-7.3/803-*` and `hack-7.3/791-*`; they
apply with zero fuzz (offsets only) and no later 7.3 patch touches their files.
The 30 generic configuration defaults added for 6.18 (Rust options and the
auxiliary-display symbols of `kmod-seg-led-gpio`) are added to
`config-7.3`; all exist in 7.3 Kconfig. Without them, selecting
`kmod-seg-led-gpio` leaves eight 7.3 symbols for interactive prompting.
`listnewconfig` with that driver enabled now reports only the three
target-supplied values that were already present before this batch. Other
incoming kernel changes are Realtek and Octeon target files, the PCA954x
autoload and new module packages; none needs an x86/64 backport.

The build-system Rust toolchain remains disabled (`USE_RUST_TOOLCHAIN` unset;
`RUST_TOOLCHAINOPTS` is a new unset symbol), so feed `rust/host` users
including glycin, librsvg and mozjs140 stay visible. Strict Kconfig checking
of a copy of `.config` reports only `kmod-seg-led-gpio` and
`RUST_TOOLCHAINOPTS` as new unset symbols. The working `.config` is unchanged.

The mainline updater then advanced Linux 7.3 to **7.3.1** (SHA256
`fa595aad93734f829c963c2a90ef7c3673224fd7fdae7b49406e397cde2de231`); all
319 carried patches apply to it with `--fuzz=0`, so 7.3.1 absorbs none of
them. 7.3.1 still lacks the RM500Q-AE binding; the three earlier
optional-feature findings remain open.

All 513 source-patch registry entries and all 319 ported patches have
matching SHA256 values. The packages, LuCI and two Passwall feeds merge 26,
42, one and one incoming commits without conflict. Routing, telephony, video
and taskplan had no incoming commits. The custom updater advances libostree
to 2026.6, tpm2-tss to 4.2.1 and wireplumber to 0.5.19; each source verifies
and prepares with its local patches. Five entries retain their review
branch. Mainline-updater (20), kernel-input (7), custom-updater (43),
package metadata/Kconfig (4) and APK source-version (2) tests pass.

This is source integration and patch-application validation. No Rust
toolchain was available (`bindgen` is absent), so the Rust patches were checked
against the C callback signature rather than compiled. The 7.3.1 kernel, a
firmware image and the updated packages were not built. No packages were
published, nothing was deployed to a device, and nothing was pushed.
Backup branches are `backup/pre-sync-20261031T041546Z` in the main tree and
in each feed.

### Main/feed synchronization and new-patch review, 2026-11-02

Merged 56 main-tree commits through `554f401d6b` into local merge
`97695f70d9`, keeping the Linux 7.3 selection and local integration. The only
conflict was the PPP release again: upstream advanced it to 6 for the jailed
pppd secrets, options-file and PPTP socket changes, while the local tree had
already published `2.5.4-r7`. The merged recipe therefore uses
`PKG_RELEASE:=8`.

The incoming 6.18 changes are the 6.18.56 to 6.18.60 stable bumps, the
removal of the `pending-6.12` leftovers, `CONFIG_CC_HAVE_*` filtering in the
shared `config-filter`, and the Rust-exposed generic symbols. Compared with
the registry, which now records the 6.18.60 baseline:

- **No new 6.18 patches.**
- **40 patches were refreshed only.** Their added and removed lines are
  unchanged; only hunk offsets and context moved. Their source hashes were
  re-recorded.
- **One patch has changed content.** In
  `706-03-v7.2-netfilter-flowtable-bail-out-if-forward-path-cannot-b`, the
  rebase onto 6.18.57 replaces `WARN_ON_ONCE(info->num_encaps-- == 0)` with
  an explicit `num_encaps == 0` check. Linux 7.3.1 `nf_flow_table_path.c`
  already uses that check, so nothing is needed.
- **Five upstream-status backports were dropped from 6.18** after they
  landed in 6.18 stable: `438` (SPI-NAND QE bit), `782` (Quectel EG060W),
  `787` (Quectel EG120K-EA), `948` (MT7530 `get_stats64`) and `950` (cgroup
  `CLONE_INTO_CGROUP` SIGKILL). Every added C line of each patch is present in
  Linux 7.3.1, so nothing is needed. The registry entries record
  `removed_in`.

Two items did need porting to 7.3:

- **Rust-exposed config symbols.** Upstream added `DRM_NOVA`,
  `DRM_PANIC_SCREEN_QR_CODE`, `DRM_TYR`, `RUST_KERNEL_DOCTESTS` and
  `SAMPLES_RUST` to `config-6.18` because a `CONFIG_RUST=y` build otherwise
  stops at a syncconfig prompt. Generic `config-7.3` had none of them. Linux
  7.3 also adds `RUST_FWCTL_ABSTRACTIONS`, `RUST_KUNIT_TESTS` and
  `RUST_SERIAL_DEV_BUS_ABSTRACTIONS`. All eight are now unset in
  `config-7.3`. Running Linux 7.3.1's `conf --listnewconfig` on the merged
  generic, x86 and x86/64 configs, with `RUST_IS_AVAILABLE` forced on, found
  `DRM_NOVA` and `RUST_SERIAL_DEV_BUS_ABSTRACTIONS` for `CONFIG_RUST=y` alone.
  With `DRM_PANIC`, `KUNIT`, `SAMPLES` and `FWCTL=y` also enabled, it found
  all eight. Afterwards it reports none, leaving only the three
  target-supplied values that it also reports without Rust. The set of
  enabled options is identical, so the kernel ABI does not change.
  `RUST_INLINE_HELPERS` was omitted: it requires a clang-built kernel.
- **Quectel RM500Q-AE binding (finding resolved).** Upstream
  `f6985f512f82` is in Linus's tree after v7.3 and is absent from 7.3.1. It
  is restored as
  `backport-7.3/935-v7.4-bus-mhi-host-pci_generic-Add-Quectel-RM500Q-AE-support.patch`,
  and `pending-7.3/936-*` is rebased on it in its original 6.18 form. Both
  were refreshed with quilt, with zero fuzz, from the 6.18 sources. The patched
  source differs from the previous 7.3 port only by the `17cb:0306`/`17cb:5002`
  table entry. Using the kernel's own command line for a 7.3.1 module, the
  previous source compiled with no `rm500q` symbols, because the unreferenced
  configuration was discarded. The new source keeps
  `mhi_quectel_rm500q_info`, its controller configuration and its channel
  table.

The full 7.3 stack of 322 patches applies to Linux 7.3.1 with `--fuzz=0`.
The mainline updater reports 7.3.1 as current. The MAP-E tunnel and DMA-BUF
heap findings remain open.

The packages feed merged 45 incoming commits. GStreamer core, base and good
conflicted on releases; they use `PKG_RELEASE:=6`, above every published or
ledger-mapped 1.28.7 identity. nmap takes upstream 7.993-r1, and its local
`110-ncat-recv-only-single-listener.patch` was refreshed from a 73-line
offset. LuCI, both Passwall feeds and video merged 3, 3, 2 and 1 commits
without conflict. Routing fast-forwarded 2 commits; telephony and taskplan
had no incoming commits. The custom updater advances libneatvnc to 1.0.4.
`ncat-7.993-r1` and `libneatvnc-1.0.4-r1` compile. Upstream removed
dnscrypt-proxy, libdbi, libdbi-drivers, libsoc and perl-test-harness, and
their stale `package/feeds` links were deleted. None was selected.
`make defconfig` leaves every selection in `.config` unchanged.

This is source integration, patch application, Kconfig and targeted-compile
validation. `CONFIG_MHI_BUS_PCI_GENERIC` remains unset, and the RM500Q-AE
change was not tested on hardware. No kernel, image or generation was built,
nothing was published or deployed, and no router was contacted. Backup
branches are `backup/pre-upstream-20261102T023631Z` in the main tree and in
each feed. Evidence is in
`/srv/openwrt-validation/upstream-update-20261102T023631Z/`.

## Upstream synchronization review, 2026-11-03

Merged OpenWrt through `46e6335fbd` (16 incoming main-tree commits) as
`a5247e0d45`, plus 25 packages-feed commits, 1 LuCI commit and 1
`passwall_luci` commit. Telephony, video, `passwall_packages`, routing and
taskplan had nothing incoming. Backup branches are
`backup/pre-upstream-20261103T032637Z` in the main tree and in each locally
modified feed. The registry was compared with all 508 current generic/x86
6.18 source patches by SHA-256: no patch was added, none was removed since the
previous audit (the five absent entries were already recorded as upstream in
6.18.56-6.18.60), and exactly one changed.

- **Ported:** `generic/pending-6.18/456-nvmem-implement-block-NVMEM-provider.patch`
  (upstream `5b3efb652f`) fixes a use-after-free in `blk_nvmem_register()`:
  the error path read `bnv->nvmem` after `kfree(bnv)`. The same hunks are now
  in `pending-7.3/456-...`; its `block.c` section is byte-identical to the
  6.18 one, and only the Kconfig/Makefile context differs. The registry source
  and ported hashes are refreshed. The driver is optional and not enabled by
  the x86 configuration.
- **Not applicable to the 7.3 stack:** the Realtek DSA/QoS rework, rtl931x,
  ipq40xx watchdog/DTS/config changes and the Sony NCP-HG100 ART fix are all in
  board-specific 6.18 trees that keep their own kernel series.
- **Packages, not kernel patches:** mac80211 backports gain
  `ath12k/105-...assign-device-id-from-the-WSI-index` and
  `subsys/484-...don-t-estimate-airtime-for-unsupported-rate-widths`
  (`PKG_RELEASE` 11 to 12). `kselftests-bpf` and `ppp.sh` changes are
  independent of the kernel series.

Release identities: ppp (local r8, upstream r7, both published) is r9, and
pulseaudio (local r8 published, upstream r5) is r9 in the packages feed, so
neither reuses a published version. perl moves to 5.44.0-r1.

Validation: Linux 7.3.1 is still the latest release, and the archive SHA256
matches `kernel-7.3`. The updater's own `validate_patches` applies the full
7.3 stack (generic backport/pending/hack, x86, overlays) to a fresh extraction
with zero fuzz; every registered ported hash matches; the 20 updater and 7
build-input tests pass. All mac80211 patches apply with zero fuzz to the
hash-verified `backports-7.2` archive. `scripts/feeds update -i -a` and
`install -a` succeed; `make defconfig` only adds the new
`# CONFIG_PACKAGE_perlbase-source is not set` symbol, and
`conf --fatalrecursive` reports no cycle (results written to an isolated file;
the working `.config` was restored unchanged).

This is source integration and patch-application validation only. Nothing was
compiled or booted, the optional blk-nvmem driver and the mac80211 changes were
not built against Linux 7.3, nothing was published, and no router was
contacted. The three optional-feature findings above remain open.

## Upstream synchronization review, 2026-11-05

Merged OpenWrt through `b455c5b851` (122 incoming main-tree commits) as
`2ed386013b`, plus 29 packages-feed, 4 LuCI and 2 `passwall_luci` commits.
Video, telephony, routing, taskplan and `passwall_packages` had nothing
incoming. Backup branches are `backup/pre-upstream-20261105T025341Z` in the
main tree, each feed and the argon theme submodule.

Main-tree conflicts and release identities:

- `crypto-ghash/arm-ce`: upstream now appends only the module name to the
  inherited AUTOLOAD list. The local `@lt7.3` version gate is kept by
  appending `$(call version_filter,ghash-arm-ce@lt7.3)`.
- dnsmasq (local r11 published, upstream r12) is r13. Upstream's new
  `230-Quieten-the-PID-file-chown-failure...` patch took the number of the
  local nftset patch, which is renamed `240-nftset-netlink-address-sets.patch`
  (still applied last). busybox (local r8, upstream r4) is r9.
- procd moves to the 2026-11-03 snapshot; the four local procd patches and all
  dnsmasq patches apply under quilt with no fuzz.

### Kernel patches: 66 new and 6 changed 6.18 sources

All 574 current generic/x86 6.18 patches were compared with the registry by
SHA-256. Classification was by application against a fresh, hash-verified
Linux 7.3.1 extraction carrying the full 7.3 stack, not by filename.

| Group | Count | Disposition |
| --- | ---: | --- |
| Backports `050`, `200`, `856-01..03`, `967-01..35` (YT921x DSA/tagger, Motorcomm PHY, xhci recovery, deferred-probe Kconfig, u-boot-env) | 40 | **Upstream in 7.3.** The ordered `967` and `856` series reverse-apply as a whole. Where a single patch's reverse fails (`856-03`, `967-02`, `967-33`, `967-34`), its added lines are present in 7.3 and only later upstream context differs, e.g. the `BIT()` endpoint-state conversion for `EP_DROP_PENDING`. |
| Pending/hack patches that apply unchanged | 22 | **Carried** unchanged into `pending-7.3`/`hack-7.3`: DSA bridge VLAN-protocol and multicast-snooping hooks (`644`, `645`), u-boot-env post-processing (`805-01/02/04`) and probe-defer hack, the YT922x DSA/PPE series, the MediaTek YT922x checksum hack and the MIPS `genvdso` warning hack. |
| `805-03`, `967-27`, `967-36`, `967-40` | 4 | **Rebased.** `805-03`: `linux/hex.h` context. `967-27`/`967-40`: Linux 7.3 already uses DSA tag values through 36, so `YT922X` and `YT922X_4B` take 37 and 38 (6.18 uses 33/34). Tag values are kernel-internal, not ABI shared with 6.18. `967-36`: `motorcomm.c` header context. |
| Changed `704`, `740`, `755`, `760-02`, `760-09`, `904` | 6 | **Context only.** The added and removed lines are unchanged, and the existing 7.3 ports still apply, so only their source hashes were refreshed. |

`config-7.3` gains `# CONFIG_NET_DSA_TAG_YT921X/YT922X` and
`# CONFIG_NET_DSA_YT92XX is not set`, matching config-6.18.
`CONFIG_DRIVER_DEFERRED_PROBE_TIMEOUT=10` was already present. The x86
configuration enables none of DSA, YT92xx, the Motorcomm PHY or u-boot-env
layouts, so the selected kernel's enabled options and ABI do not change.

Validation:

- The full 7.3 stack, now **349 patches**, applies to a fresh 7.3.1
  extraction (SHA256 `fa595aad...de231`, matching `kernel-7.3`) with
  `--fuzz=0`. The mainline updater reports 7.3.1 as current.
- Using the existing x86/64 7.3.1 kernel config with `COMPILE_TEST`, DSA,
  `NET_DSA_YT92XX`, `MOTORCOMM_PHY`, `NET_MEDIATEK_SOC` and the u-boot-env layout
  enabled in a scratch copy, OpenWrt GCC 14.4.0 compiles `yt921x.o`,
  `tag_yt921x.o`, `tag_yt922x.o`, DSA `port.o`/`user.o`/`dsa.o`, `motorcomm.o`,
  `phy-c45.o`, `u-boot-env.o` and MediaTek `mtk_ppe.o`, `mtk_ppe_offload.o`
  and `mtk_eth_soc.o` with zero warnings. The MIPS `genvdso` hack was not
  compiled.
- The registry covers all 574 present sources plus 5 removed entries. There
  are no missing or stale sources, and every one of the 349 7.3 patches is
  registered with a matching hash. The mainline-updater and kernel-input tests
  pass.

Kernel package definitions also change upstream (AUTOLOAD names without
`.ko`, dropped non-existent modules, new `kmod-can-mcp251xfd`, `kmod-can-vxcan`
and `kmod-serial-sc16is7xx`). kmod payloads change, but their identity
carries the kernel sequence, so the next reserved generation covers them.

Feeds: the packages merge conflicted only on docker-compose, which takes
upstream 5.7.0-r1 while keeping the local dependency without `+docker`. The
`passwall_luci` merge keeps the local independent LuCI revision versioning
instead of upstream's manual `26.11.3` version. LuCI removed the
`luci-theme-openwrt` and `-2020` themes (neither selected); their stale
`package/feeds` links were deleted. On a copy, `make defconfig` changes only
upstream's new busybox `TRACEROUTE_USE_ICMP` default, the new
`kmod-serial-sc16is7xx` symbol and the removed themes. The working `.config`
is unchanged.

The custom updater advances glycin to 2.2.6, libibus to 1.5.35 and
luci-theme-argon to 3.1.2. Seven entries keep their review branch: flatpak
1.19, freerdp 3.33, gcr 4, intel-media-driver, GTK 4, the libibus tag noise and
libvirt 12.9. Both new sources pass hash verification and apply their local
patches with no fuzz. libubox, procd (with its four systemd patches) and
dnsmasq-full 2.93-r13 (with the nftset fast path) compile. glycin and libibus
were prepared but not compiled.

This is source integration, patch application and focused object compilation.
No full kernel, image or generation was built, nothing was published, and no
router was contacted. The MAP-E tunnel and DMA-BUF heap findings remain open.

## Upstream synchronization review and Linux 7.3.3, 2026-11-07

Merged OpenWrt through `7e8bfcfe76` (45 incoming main-tree commits) as
`aa58ff474f`, plus 20 packages-feed, 3 LuCI, 5 video and 6 `passwall_luci`
commits. Telephony, routing, taskplan and `passwall_packages` had nothing
incoming. Backup branches are `backup/pre-upstream-20261107T033226Z` in the
main tree, each feed and the argon theme submodule.

Main-tree conflicts and release identities (checked against the published
feed and the ELF rebuild ledger):

- procd (2026.11.03 published at r6, upstream r2) is r7; busybox (r10 and r11
  published, upstream r5 for the new shell-history controls) is r12.
- Upstream adds `/dev/dma_heap/*` to the video group in `30-video.json`.
  systemd 262 has no `dma_heap` rule, so `60-openwrt-video.rules` gains the
  same policy for native systemd, and hardware-support moves to r4 past the
  published video-support 3.

Feed conflicts: openssh takes upstream 10.6p2-r1 and fuse3 3.18.3-r1 (both
new versions), keeping local recipe changes. Mesa takes upstream's
`LIBMESA_PROVIDERS` conflict chain; the local `libmesa-virtualization` variant
joins it (evaluated before `libmesa-softpipe`, which stays last) and keeps the
local `+accel-support`. Mesa (26.2.2-r8 published, upstream r4) is r9. The
packages feed drops libpbc, libuwsc, libstrophe, libsocketcan, libroxml,
libpqxx, libopen62541 and libnopoll; none is selected or depended upon, and
their stale `package/feeds` links were deleted. On a copy, `make defconfig`
changes only upstream's busybox history defaults, the new DW HDMI audio
symbols, the dropped packages and udp-broadcast-relay-redux;
`conf --fatalrecursive` reports no cycle. The working `.config` is unchanged.

The custom updater advances fastfetch to 2.71.0 and luci-theme-argon to 3.1.3.
gtk-vnc 1.6 is a new review branch beside flatpak 1.19, gcr 4,
intel-media-driver, GTK 4 and the libibus tag noise. procd, busybox, fastfetch,
openssh, fuse3 and mesa prepare with all local patches and no fuzz.

### Kernel patches: one changed 6.18 source, DMA-BUF heap finding resolved

All 574 generic/x86 6.18 sources were compared with the registry by SHA-256:
none was added or removed and exactly one changed.
`hack-6.18/904-debloat_dma_buf.patch` (upstream `b12b44bfdf`) is the fix for
the open `dmabuf-heaps-kbuild` finding: the heap objects are listed by path in
`drivers/dma-buf/Makefile` and linked into `dma-shared-buffer`, and the
unread `heaps/Makefile` rewrite is dropped. `hack-7.3/904` is ported the same
way, with the `heaps/` descent removed so the objects are not built twice.
`DMABUF_HEAPS` is a bool that selects `DMA_SHARED_BUFFER`, so the composite is
built in whenever heaps are enabled and its several initcalls cannot collide in
a module. With `DMABUF_HEAPS_SYSTEM` and `DMABUF_HEAPS_CMA` enabled in a scratch
copy of the x86 configuration, `system_heap.o` and `cma_heap.o` are now in
`drivers/dma-buf/built-in.a`. x86 leaves `DMABUF_HEAPS` unset, so its enabled
options and ABI are unchanged. The finding is marked resolved in the registry.

Other kernel-side changes are board-specific (realtek, qualcommax, mpc85xx,
rockchip, airoha) or kmod package definitions (Panfrost, DW HDMI I2S/AHB audio,
early Marvell PHY autoload), and mac80211 gains ath11k/ath12k backports
(r13).

### Linux 7.3.1 to 7.3.3

`update-mainline-kernel.py --update` verified the 7.3.3 archive (SHA256
`79c66dde...4f3d1`) and applied the full 349-patch stack with `--fuzz=0`
before rewriting `kernel-7.3`. 456 files changed between 7.3.1 and 7.3.3; no
Kconfig file is among them, and `listnewconfig` against the x86 7.3.1
configuration reports nothing, so `olddefconfig` changes only the version
banner. Ten stable-changed files are also touched by local patches
(`drivers/base/core.c`, `drivers/nvmem/core.c`, `io_uring/zcrx.c`,
`kernel/fork.c`, `lib/kobject_uevent.c`, `net/8021q/vlan_dev.c`,
`net/core/{dev,rtnetlink,skbuff}.c` and the top Makefile). With OpenWrt
GCC 14.4.0 and the x86 configuration (plus NVMEM and the DMA-BUF heaps, which
x86 does not enable), all nine objects and `drivers/dma-buf/` compile with no
warnings. All registry source and ported hashes match and the 20 updater
tests pass.

This is source integration, patch application and focused object compilation.
No full kernel, image or generation was built, nothing was published, and no
router was contacted. The kernel version change requires a new reserved
generation. The MAP-E tunnel finding remains open.

## Upstream synchronization review, 2026-11-08

Merged OpenWrt through `3236b6ae94` (13 incoming main-tree commits) as
`922a0a6535`, plus 4 packages-feed (`0a0481aba`), 5 LuCI (`b0176a7c6c`), 1
video (`1ff9c26`) and 2 `passwall_luci` (`112cc368`) commits. Telephony,
routing, taskplan and `passwall_packages` had nothing incoming. Backup
branches are `backup/pre-upstream-20261108T121754Z` in the main tree, each
feed and the argon theme submodule.

### Kernel patches: no generic or x86 6.18 changes

All 13 incoming main-tree commits touch only board-specific trees (`airoha`
EN7581 thermal sensor, `ath79` PCI/PCIe/INTC rework, and `realtek` DSA/FDB/PIE
driver updates) that retain their own 6.18 kernel series:

- All 574 present generic/x86 6.18 source patches and 5 recorded removed
  entries in `configs/mainline-kernel-patches.json` match by SHA-256: no
  generic or x86 6.18 patch was added, modified or removed.
- All 349 carried Linux 7.3 patches match their registered SHA-256 values and
  apply to a fresh extraction of the verified Linux 7.3.3 archive (SHA256
  `79c66dde...4f3d1`) with `--fuzz=0`.
- `update-mainline-kernel.py --check` confirms Linux 7.3.3 remains the latest
  upstream release in the 7.3 series. No new 6.18-to-7.3 backport is needed.

### Feeds and custom packages

All feed merges completed without conflicts or local-feature regressions:

- `packages`: updates `python3` to `3.14.10-r1`, `python-pip` to `26.2.2-r1`,
  `rsyslog` to `8.2606.0-r3`, and `bcm27xx-eeprom` to `2026.11.03~be236766-r1`.
- `luci`: updates `luci-mod-dashboard` (temperature monitoring and live chart
  improvements), `luci-app-qosify`, and `luci-app-usteer`.
- `video`: updates `wpewebkit` to `2.54.2-r6` (in-memory network session cache
  option), preserving all local GStreamer, colorimetry, Kodi hole-punch and EME
  patches.
- `passwall_luci`: extracts optional node DNS from Clash subscriptions and
  fixes component update button clipping while retaining local Git-derived
  LuCI revision versioning.
- `update-custom-packages.py --update` checked all 170 registered custom
  packages: 130 are current, 34 are local, and 6 remain on their configured
  review branches (`flatpak` 1.19.2, `gcr3` 4.4, `gtk-vnc` 1.6,
  `intel-media-driver` 600.0132, `libgtk3` 4.24, `libibus` tag noise). No
  custom recipe required a version bump.

Validation: `python3` 3.14.10, `python-pip` 26.2.2 and `wpewebkit` 2.54.2-r6
download, verify SHA-256 and apply all patches cleanly via `make .../prepare`.
`./scripts/feeds update -i -a` and `./scripts/feeds install -a` succeed with
all nine feed indexes nonempty and zero broken `package/feeds` links. Strict
`conf --fatalrecursive` on an isolated copy of `.config` reports no Kconfig
cycles and zero configuration changes, leaving the working `.config`
untouched. The mainline-updater (20), custom-updater (47), kernel-input (7)
and package-metadata/Kconfig (4) test suites pass.

This is source integration, patch-application and Kconfig validation only. No
kernel, firmware image or APK generation was built, nothing was published, and
no router was contacted. The optional MAP-E tunnel finding remains open.

## Upstream synchronization review, 2026-11-10

Merged OpenWrt through `3d5a743f1f` (8 incoming main-tree commits since
`7edc67adad`) as `41bcc0ec80`, plus 8 packages-feed (`85172e13b`), 1 LuCI
(`5db150c176`), 3 `passwall_luci` (`ff019682`) and 4 `passwall_packages`
(`fbb5761`) commits. Telephony, routing, taskplan and video had nothing
incoming. Backup branches are `backup/pre-upstream-20261110T080047Z` in the
main tree, each feed and the argon theme submodule.

### Kernel patches: no generic or x86 6.18 changes

The incoming main-tree commits since the 2026-11-08 review (`3236b6ae94..3d5a743f1f`)
touch only board-specific trees (`ath79` PCI radio path migration and patch
refresh, `qualcommax` IPQ50xx unused MDIO patch removal, `realtek` RTL930x L3
host hash updates), out-of-tree Realtek NIC packages (`r8125` 9.018.00, `r8126`
10.018.00, `r8127` 11.017.02, `r8168` 8.057.00, all unselected in the x86/64
config), `tools/ccache` 4.14.2, and `ppp` 2.5.5:

- All 574 present generic/x86 6.18 source patches and 5 recorded removed
  entries in `configs/mainline-kernel-patches.json` match by SHA-256: no
  generic or x86 6.18 patch was added, modified or removed.
- All 349 carried Linux 7.3 patches match their registered SHA-256 values and
  apply to a fresh extraction of the verified Linux 7.3.3 archive (SHA256
  `79c66dde...4f3d1`) with `--fuzz=0`.
- `update-mainline-kernel.py --check` confirms Linux 7.3.3 remains the latest
  upstream release in the 7.3 series. No new 6.18-to-7.3 backport is needed.

### Main tree, feeds and custom packages

- `main`: `ppp` updates from `2.5.4-r9` to `2.5.5-r1` (switching credentials
  passing in `ppp.sh` from `file` `.opts` to `+ua` `.creds` while preserving
  unprivileged `ppp` jail ownership).
- `packages`: updates `ddns-scripts` to `2.8.5-r1`, `weechat` to `4.10.4-r1`
  (retaining the local default-provider conflict comment on `weechat-minimal`),
  `shunt` to `0.4.2-r1`, `domoticz` to `2026.4-r1`, `dawn` to `2026-11-09`
  Git HEAD, and `rsync` to `3.5.2-r1` (CVE-2026-119741).
- `luci`: updates `luci-app-uhttpd` (`rmempty = false` on default `/www` home).
- `passwall_luci`: updates `iptables.sh` and `nftables.sh` (ISP DNS bypass set
  placement, disabling `auto-merge` on dynamic nftsets, and shunt set cleanup
  on stop) while preserving local Git-derived version calculation.
- `passwall_packages`: updates `v2ray-geoip` (`202611050019`), `v2ray-geosite`
  (`202611082203`), and `smartdns` (`48.5_rc1`).
- `update-custom-packages.py --update` checked all registered custom packages
  and `luci-theme-argon` (`3.1.3`): 130 are current, 34 are local, and 6 remain
  on their configured review branches. No custom recipe required a version bump.

Validation: `ppp` 2.5.5, `rsync` 3.5.2 and `v2ray-geodata` download, verify
SHA-256 and apply all patches cleanly via `make .../prepare`.
`./scripts/feeds update -i -a` and `./scripts/feeds install -a` succeed with
all nine feed indexes nonempty and zero broken `package/feeds` links. Strict
`conf --fatalrecursive` on an isolated copy of `.config` reports no Kconfig
cycles and zero configuration changes, leaving the working `.config`
untouched. The mainline-updater (20), custom-updater (47) and kernel-upgrade
(41) test suites pass.

This is source integration, patch-application and Kconfig validation only. No
kernel, firmware image or APK generation was built, nothing was published, and
no router was contacted. The optional MAP-E tunnel finding remains open.

## Upstream synchronization review, 2026-11-11

Merged OpenWrt through `89e69d9391` (1 incoming main-tree commit since
`3d5a743f1f`) as `45f717a78a`, plus 10 packages-feed (`b8c228029`), 1 LuCI
(`e5be8068c5`), 11 video (`85dc230`) and 6 `passwall_luci` (`995980a1`)
commits. Telephony, routing, taskplan and `passwall_packages` had nothing
incoming. Backup branches are `backup/pre-upstream-20261111T022457Z` in the
main tree, each feed and the argon theme submodule.

### Kernel patches: no generic or x86 6.18 changes

The single incoming main-tree commit since the 2026-11-10 review
(`3d5a743f1f..89e69d9391`) touches only `target/linux/ath79/image/generic.mk`
(D-Link DIR-825 B1 supported device alias):

- All 574 present generic/x86 6.18 source patches and 5 recorded removed
  entries in `configs/mainline-kernel-patches.json` match by SHA-256: no
  generic or x86 6.18 patch was added, modified or removed.
- All 349 carried Linux 7.3 patches match their registered SHA-256 values and
  apply to a fresh extraction of the verified Linux 7.3.3 archive (SHA256
  `79c66dde...4f3d1`) with `--fuzz=0`. No new 6.18-to-7.3 backport is needed.
- `update-mainline-kernel.py --check` reports upstream Linux `7.3.4` is newly
  available on kernel.org while the working tree remains pinned at `7.3.3`
  pending an explicit kernel point-release update.

### Feeds and custom packages

- `packages`: updates `golang1.27` to `1.27.4-r1`, `shunt` to `0.4.5-r1`,
  `owut` to `2026.11.08-r1`, `delve` to `1.27.2-r1`, `django` to `6.1.3-r1`,
  `python-sqlparse` to `0.6.1-r1`, `python-asgiref` to `3.13.0-r1`, `frp` to
  `0.71.1-r1`, `stress-ng` to `0.22.01-r1`, and `libmaxminddb` to `1.14.1-r1`.
- `luci`: updates `luci-app-shunt` to sync with `shunt` 0.4.5.
- `video`: adds initial Qt 6 framework recipes (`qt6base`, `qt6quick`,
  `qt6shadertools`, `qt6svg`, `qt6tools`, `qt6translations`, all unselected in
  `.config`) and enables shared host library building in `libdouble-conversion`.
- `passwall_luci`: adds socks/http/https and WireGuard URI import/export, fixes
  Xray Hysteria2 port hopping and sing-box `ws` path query handling, while
  preserving local Git-derived LuCI revision calculation in
  `luci-app-passwall/Makefile`.
- `update-custom-packages.py --update` checked all registered custom packages
  and `luci-theme-argon` (`3.1.3`), advancing `appstream` (`1.2.2 -> 1.2.3`),
  `firefox-esr-bin` (`153.6.0esr -> 153.7.0esr`), `freerdp` (`3.33.0 -> 3.33.1`),
  and `xwayland` (`24.1.14 -> 24.1.15`). Follow-up review of the 6 pending
  `review` entries advanced `gtk-vnc` from `1.5.0` to `1.6.0` (`1.6/` series),
  leaving the remaining 5 entries (`flatpak` 1.19 prerelease, dual-slot `gcr3`
  / `libgtk3`, and upstream tag noise in `intel-media-driver` / `libibus`) on
  their stable branches.

Validation and publication: `appstream` 1.2.3, `firefox-esr-bin` 153.7.0esr,
`freerdp` 3.33.1, `xwayland` 24.1.15 and `gtk-vnc` 1.6.0 download, verify
SHA-256 and apply all patches cleanly. `./scripts/build-and-publish.sh -j16
--allocate-rebuilds` built the full tree while reusing unchanged kernel
generation `7.3.3-58-openwrt`, allocated `daed` `2.1.1-r9` in
`configs/apk-elf-rebuilds.mk` for the Go 1.27.4 compiler rebuild, passed the
live-router upgrade preflight simulation, and published userspace snapshot
`20261111T031320.195084Z` (11 updated APKs: `appstream-1.2.3-r1`,
`daed-2.1.1-r9`, `firefox-esr-bin-153.7.0-r1`, `gtk-vnc-1.6.0-r1`,
`libfreerdp3-3.33.1-r1`, `libwinpr3-3.33.1-r1`, `winpr-hash-3.33.1-r1`,
`xwayland-24.1.15-r1`, `luci-app-passwall-26.315.08841~995980a`,
`luci-i18n-passwall-zh-cn-26.314.59753~596ca9c`, and
`base-files-1755.9~89e69d9391`). No packages were installed onto the physical
router. The optional MAP-E tunnel finding remains open.

## Upstream synchronization review, 2026-11-13

Merged OpenWrt through `24c13d794c` (37 incoming main-tree commits since
`ada52cc7ed`), plus 4 packages-feed (`66689386b`), 2 LuCI (`326145c239`), 2
video (`97137d9`) and 1 `passwall_luci` (`aada0ff4`) commits. Telephony,
routing, taskplan and `passwall_packages` had nothing incoming. Backup branches
are `backup/pre-upstream-20261113T141007Z` in the main tree, each feed and the
argon theme submodule.

### Kernel patches: 5 new and 6 changed 6.18 sources ported to Linux 7.3

Two incoming main-tree commits (`0642965749` and `7b26f9c0d8`) touch
`target/linux/generic/*-6.18/`:

- Five new `backport-6.18` patches target upstream v7.4/v7.5 and are absent
  from Linux 7.3.4 (`b11b6df8...fd1f`). All five are ported to
  `target/linux/generic/backport-7.3/` with zero fuzz:
  - `757-v7.5-net-sfp-add-quirk-for-OEM-SFP-ONU-XGSPON.patch` (`drivers/net/phy/sfp.c`)
  - `802-01-v7.4-net-usb-lan78xx-register-the-PHY-interrupt-with-the-.patch` (`drivers/net/usb/lan78xx.c`)
  - `802-02-v7.4-net-usb-smsc95xx-register-the-PHY-interrupt-with-the.patch` (`drivers/net/usb/smsc95xx.c`)
  - `802-03-v7.4-net-phy-take-the-interrupt-back-from-the-bus-on-deta.patch` (`drivers/net/phy/phy_device.c`)
  - `802-04-v7.4-net-phy-restore-the-interrupt-when-the-generic-bind-.patch` (`drivers/net/phy/phy_device.c`)
- Six `pending-6.18` patches (`750`, `751`, `752`, `753`, `801-01`, `896-03`)
  changed hunk line offsets only due to the new `757`/`802` backports; their
  corresponding `pending-7.3` patches and `configs/mainline-kernel-patches.json`
  entries are refreshed to match.
- All 354 carried Linux 7.3 patches match their registered SHA-256 values and
  apply to a fresh extraction of Linux 7.3.4 with `--fuzz=0`.
  `update-mainline-kernel.py --check` reports `7.3.4` is `current`.

### Main tree, feeds and custom packages

- `main`: deduplicates `KernelPackage/hid-multitouch` in
  `package/kernel/linux/modules/input.mk` in favor of upstream's `b0f96dc621`,
  and refreshes `package/network/config/firewall4/patches/*` against
  `firewall4` `2026-11-08` (`3722eadc`, which dropped the commented
  `disable_ipv6` line from `root/etc/config/firewall`). `fstools` updates to
  `2026-11-07` (`5e371ecf`) with both local overlay patches applying cleanly.
- `packages`: updates `apache` to `2.4.71`, `git-lfs` to `3.8.1`, and
  `ddns-scripts` (HTTPS URL settings and removal of `cnkuai.cn`).
- `luci`: merges Weblate translation updates while retaining local `firewall`,
  `ttyd`, `status`, `daed`, `needrestart` and `uci-history` views.
- `video`: updates `wpewebkit` and accepts upstream `97137d9` dropping
  `frameworks/wayland/files/video.hotplug` (`wayland` bumped to `1.26.0-r4`),
  since both `hardware-support` (`30-video.json`/`35-accel.json`) and
  `systemd-udevd` (`50-udev-default.rules`) already assign `video` to display
  cards and preserve `render` on `renderD*` nodes; local `xdg-runtime-dir.profile`
  login-session preservation remains intact.
- `passwall_luci`: adds proxy warm-up before node latency tests.
- `update-custom-packages.py` advances `tpm2-tss` (`4.2.1 -> 4.2.2`),
  `luci-theme-argon` (`3.1.3 -> 3.1.4`, submodule `148cc76`), `cmake-bin`
  (`4.4.5 -> 4.5.0`) and `libudisks2` (`2.11.2 -> 2.12.0`). The remaining 5
  `review` entries (`flatpak` 1.19 prerelease, dual-slot `gcr3`/`libgtk3`, and
  upstream tag noise in `intel-media-driver`/`libibus`) stay on their pinned
  stable branches.

Validation: `./scripts/feeds update -i -a`, `./scripts/feeds install -a` and
`make defconfig` succeed with zero `.config` changes; `tpm2-tss`, `cmake-bin`,
`libudisks2`, `fstools` and `firewall4` prepare/compile cleanly, and the
mainline-kernel, custom-package and LuCI firewall test suites pass. No firmware
or APK feed was published and no router was modified. The optional MAP-E tunnel
finding remains open.

## Upstream synchronization review, 2026-11-14

Merged OpenWrt through `e2ed57b957` (7 incoming main-tree commits since
`24c13d794c`) as `8fc9b983fd`, plus 1 packages-feed (`b986e7a60`) commit as
`9c6a80d3c`. LuCI, video, telephony, routing, taskplan, `passwall_packages` and
`passwall_luci` had nothing incoming. Backup branches are
`backup/pre-upstream-20261114T035414Z` in the main tree, each feed and the
argon theme submodule.

### Kernel patches: no generic or x86 6.18 changes

All 7 incoming main-tree commits (`ea807f4842..e2ed57b957`) touch only
`target/linux/realtek/` (`files-6.18/drivers/net/pcs/pcs-rtl-otto.c` and
`patches-6.18/744-net-phylink-pass-media-to-PCS-configuration.patch`):

- All 580 present generic/x86 6.18 source patches and 5 recorded removed
  entries in `configs/mainline-kernel-patches.json` match by SHA-256: no
  generic or x86 6.18 patch was added, modified or removed.
- All 354 carried Linux 7.3 patches match their registered SHA-256 values and
  apply to a fresh extraction of Linux 7.3.4 (`b11b6df8...fd1f`) with
  `--fuzz=0`. No new 6.18-to-7.3 backport is needed.
- `update-mainline-kernel.py --check` reports `7.3.4` is `current`.

### Feeds and custom packages

- `packages`: adds host build support to `libjpeg-turbo` (`b986e7a60`) without
  changing target package contents or version (`3.1.1-r3`, mapped to `3.1.1-r4`
  in `configs/apk-elf-rebuilds.mk`).
- `update-custom-packages.py` advances `libostree` (`2026.6 -> 2026.7`). The
  remaining 5 `review` entries (`flatpak` 1.19 prerelease, dual-slot `gcr3` /
  `libgtk3`, and upstream tag noise in `intel-media-driver` / `libibus`) stay
  on their pinned stable branches.

Validation: `./scripts/feeds update -i -a`, `./scripts/feeds install -a` and
`make defconfig` succeed with zero `.config` changes; `libostree` and
`libjpeg-turbo` prepare/compile cleanly, and the mainline-kernel and
custom-package test suites pass. No firmware or APK feed was published and no
router was modified. The optional MAP-E tunnel finding remains open.

## Upstream synchronization review, 2026-11-16

Merged 131 incoming main-tree commits through `7424e2ca30` as `7a085bfd72`,
plus 7 packages, 1 LuCI, 8 telephony, 3 Passwall LuCI and 1 Passwall packages
commits. Routing, taskplan and video were already current. Preservation
snapshots and backup branches cover all 11 repositories, including the Argon
submodule and retired Argon configuration repository. Evidence is under
`.git/pull-preserve/20261116T013030Z/` and the `.git/*current.log` /
`.git/sync-package-*.log` logs.

### Kernel: no new backport required for the selected x86/64 configuration

OpenWrt commit `b828f58d67` adds three generic 6.18 patches, `799-01` through
`799-03`, fixing MediaTek WED stale freed pointers, reset buffer leaks and
failed receive-buffer initialization. All changes target
`drivers/net/ethernet/mediatek/mtk_wed.c`. Its Kconfig requires the MediaTek
SoC platform or `COMPILE_TEST`; this x86/64 configuration enables neither.
The changed existing `799-net-ethernet-mtk_wed-attach-*` patch only refreshes
hunk offsets. There are no incoming x86/64 kernel patch changes; the Geode
image feed-package adjustment concerns a different subtarget.

These three WED fixes remain optional 7.3 port candidates if MediaTek SoC
support or compile testing is enabled later. No kernel patch was changed by
this check. The registry is intentionally unchanged: the current inventory
has 583 generic/x86 6.18 source patches, three unregistered new WED sources,
one changed source hash (the offset-only `799` refresh), and five previously
recorded removed sources. Do not treat the registry as hash-current for the
new 6.18 stack. All 354 carried 7.3 patches, including four additions, still
match their registered hashes and apply with `--fuzz=0` to a fresh extraction
of SHA256-verified Linux 7.3.4 (`b11b6df8...fd1f`). The release checker reports
7.3.4 current. Hash and application receipts are in `kernel-*-audit.json`
and `kernel-apply-result.json` within the preservation directory.

Incoming wireless fixes are carried by the separate mac80211 backports and
hostapd packages. Both packages prepare successfully with the existing local
patches; they do not require duplicate patches in the native 7.3 stack.

### Integration repairs and custom packages

- Resolve the FFmpeg release conflict as `9.0.1-r9`, retaining local GNOME,
  VA-API and library selections while accepting upstream patches. FFmpeg
  preparation passes with the merged patch stack.
- Refresh both local ubox patches using `make package/system/ubox/refresh`.
  Preserve upstream's bounded whitespace trim and kernel-line truncation in
  the mutable syslog input path before entering the const journal-compatible
  storage API. Journal reader, forwarding/reconnect and versioned kernel
  autoload support remain present. The target ubox/logd build passes.
- Make the logd test choose the recipe's exact source archive, allowing old
  and new downloads to coexist, and update its event-loop stub to match
  current libubox headers. All three tests execute and pass without skips.
- Strict Kconfig exposed an existing QEMU io_uring/package dependency cycle.
  Move the AIO options outside the emulator package guard, following the
  existing graphics/audio option arrangement. Strict validation passes with
  zero selected-symbol differences from the preserved `.config`. The feed
  edit is mirrored by `configs/qemu-aio-kconfig-feeds.json` and
  `patches/feeds/0039-packages-qemu-aio-kconfig.patch`.
- Custom update report `logs/custom-package-updates/20261116T013124.749290Z/report.json`
  passes for all 188 entries: 147 current, 36 locally maintained and 5 review
  entries; no eligible custom recipe update is available.

Validation: mainline updater (20), kernel build inputs (7), custom updater
(49), package metadata/Kconfig (4), and logd journal (3) tests pass. Feed
update/install, metadata generation, all nine nonempty indexes, generated
link checks and preservation checks pass. The preserved `.config`, overlays,
stashes and original untracked contents are unchanged; every original
repository HEAD remains an ancestor. Integration repairs and this report are
left uncommitted for review. No full firmware build or runtime test was run:
this request covers source synchronization and patch applicability. No feed
publication, Git push, router installation, service restart or reboot occurred.

## Upstream synchronization review, 2026-11-17

OpenWrt through `393efd7d74ce` adds two generic SDIO initialization fixes
(`445-01` and `445-02`, upstream v7.5). Both are absent from Linux 7.3.4
and apply to the full local stack with zero fuzz and no offsets. MMC/SDHCI
is enabled in the x86 kernel, so these are recommended backport candidates
for SDIO correctness. No affected physical card was verified, and the
7.3 patch stack was not changed by this applicability check. There are no
incoming x86-specific patches. All 354 current 7.3 patches apply cleanly;
the registry remains intentionally behind the two SDIO and three earlier
WED source additions.

### SDIO backports completed, 2026-11-17

The requested follow-up now carries both `445-01` and `445-02` in
`target/linux/generic/backport-7.3/`, byte-identical to their upstream
6.18 copies, including commit provenance. No patch regeneration was needed.
The registry records both source/ported SHA-256 values. Its three earlier
WED additions and offset-only source-hash change remain outstanding outside
this x86 scope; the SDIO entries are current.

All 356 carried patches apply with zero fuzz to a fresh extraction of the
SHA256-verified Linux 7.3.4 archive plus current generic/x86 overlays. The
resulting patched `drivers/mmc/core/sdio.c` compiles successfully using the
existing selected x86 kernel's recorded compiler command and generated headers,
with its output/dependency file redirected to the isolated evidence directory.
The normal prepared kernel tree, full kernel image and generation number were
not rebuilt or changed. This proves patch application and compilation, not
SDIO/UHS/1.8 V behavior on physical hardware.

Evidence: `.git/sdio-bridge-20261117T023432Z/kernel-result.json` and
`sdio-compile.log`. No publication, installation, restart or reboot occurred.

Mainline updater tests pass all 20 cases. Checkpatch reports zero errors for
both carried patches and one inherited warning on the long quoted kernel-log
line in patch 445-02's upstream commit description; upstream patch bytes are
preserved.

### Subsequent full build and publication, 2026-11-17

The authorized full `-j16` build and coordinated publication completed as
`7.3.4-66-openwrt`. The fresh staged rootfs passes all 27 bridge tests, and
publication preflight passes. No VM or physical installation/reboot occurred.

### Subsequent physical boot confirmation, 2026-11-17

After the user completed installation and reboot, a read-only SSH check found
`7.3.4-66-openwrt` running and selected as both default and known-good.
The trial counter is cleared, fallback remains `7.3.4-65-openwrt`,
`kernelctl check` returns 0 and systemd reports no failed units.
The agent did not initiate this installation or reboot. This confirms the
physical boot and built-in health checks, not SDIO voltage/UHS behavior,
Wi-Fi schedule execution or desktop/client acceptance.

## Upstream synchronization review and Linux 7.3.5, 2026-11-18

Merged OpenWrt through `27663a017ad8` (19 incoming main-tree commits) as
`712beefa91`, plus 24 `packages`, 1 `luci` and 2 `passwall_luci` commits.
Backup branches are `backup/pre-upstream-20261118T033529Z` across all 11
repositories; preservation receipts and audit logs are in
`.git/pull-preserve/20261118T033529Z/`.

### Kernel patches and Linux 7.3.5 update

- **Incoming 6.18 patches**: No `target/linux/x86` files changed. One new
  generic patch landed (`c06ccca080`),
  `target/linux/generic/hack-6.18/301-03-mips-keep-module-code-out-of-the-first-32-KiB-of-a-segment.patch`,
  touching `arch/mips/kernel/module.c` only for the 32-bit MIPS 24K EPC
  erratum. It does not apply to or belong in the x86/64 Linux 7.3 port.
  Other incoming kernel changes (`airoha`, `ramips`, `realtek`, `sifiveu`,
  `sunxi`) are target-specific.
- **Linux 7.3.4 to 7.3.5**: `update-mainline-kernel.py` detected upstream
  Linux `7.3.5` (SHA-256
  `8f293f83d54f0b7b9be56863ebc5e4ea79d73e530b4ae55c572be97ef39f0990`).
  Linux 7.3.5 absorbs upstream commit `01739ccea21b`
  (`mtd: spi-nor: macronix: Restore fallback parameters for MX25L12805D`),
  which was previously carried as
  `target/linux/generic/backport-7.3/439-v7.4-mtd-spi-nor-macronix-Restore-fallback-parameters-for.patch`.
  Forced reverse dry-run against pristine 7.3.5 succeeds with zero fuzz, so
  `backport-7.3/439-*` is dropped and its entry in
  `configs/mainline-kernel-patches.json` is marked `upstream` in `7.3.5`.
- All **355 remaining carried Linux 7.3 patches** match their registered
  hashes and apply to a fresh extraction of SHA256-verified Linux 7.3.5 plus
  current generic/x86 overlays with `--fuzz=0`. `target/linux/generic/kernel-7.3`
  is updated to `7.3.5`.
- Between 7.3.4 and 7.3.5, 467 files changed; the only Kconfig change is in
  `lib/crypto/Kconfig` (`MIPS && CPU_CAVIUM_OCTEON && CPU_BIG_ENDIAN` defaults
  for SHA1/SHA256/SHA512), leaving the x86/64 kernel configuration unchanged.
  The optional MAP-E tunnel finding remains open.

## Upstream synchronization review, 2026-11-19

Merged OpenWrt through `ecd9120f0451` (8 incoming main-tree commits) as
`5009212efb`, plus 23 `packages`, 1 `luci`, and 2 `passwall_luci` commits.
Backup branches are `backup/pre-upstream-20261119T020337Z` across all 11
repositories; preservation receipts and audit logs are in
`.git/pull-preserve/20261119T020337Z/`.

- **Mainline Linux 7.3**: `update-mainline-kernel.py --check` reports Linux
  `7.3.5` (`8f293f83d54f0b7b9be56863ebc5e4ea79d73e530b4ae55c572be97ef39f0990`)
  is current.
- **Incoming 6.18 patches**: Zero files under `target/linux/generic/` or
  `target/linux/x86/` were added, modified, or removed. The only incoming
  kernel changes are target-specific (`qualcommax` IPQ50xx and `realtek`
  `mdio-realtek-otto-serdes.c` / DTS / `hwmon_fancontrol`).
- **Full 6.18 / 7.3 audit**: The 586-patch generic/x86 6.18 stack has no new
  backport candidates; the four unregistered 6.18 patches remain the previously
  reviewed non-x86 entries (`hack-6.18/301-03-mips-*` and
  `pending-6.18/799-01..03` MediaTek WED, plus the offset-only `799` refresh).
  All **355 carried Linux 7.3 patches** match their registered SHA-256 hashes
  and apply with `--fuzz=0` to a fresh extraction of verified Linux `7.3.5` plus
  current generic/x86 overlays. The optional MAP-E tunnel finding remains open.

## Upstream synchronization review, 2026-11-20

Merged OpenWrt through `8b34d6283fc5` (21 incoming main-tree commits, including
the `6.18.60` -> `6.18.64` stable bumps and GCC default 15 switch) as
`49f4f53f74`, plus 20 `packages`, 7 `luci`, 3 `passwall_luci`, and 1 `video`
commits. Backup branches are `backup/pre-upstream-20261120T015903Z` across all
repositories; preservation receipts and audit logs are in
`.git/pull-preserve/20261120T015903Z/`.

- **Mainline Linux 7.3**: `update-mainline-kernel.py --check` reports Linux
  `7.3.5` (`8f293f83d54f0b7b9be56863ebc5e4ea79d73e530b4ae55c572be97ef39f0990`)
  is current.
- **Incoming 6.18 patches**: Zero files under `target/linux/x86/` changed. Six
  dropped `backport-6.18` patches (`439`, `441`, `503-01`, `734`, `755`,
  `856-01`) are already upstream in Linux `7.3.5`; 58 generic patches had
  context/hunk-only refreshes (plus `pending-6.18/739-03` for the non-x86
  MT7988 Lynxi PCS driver). Two new generic patches landed in commit
  `93f90a5385` for `drivers/net/phy/realtek/realtek_hwmon.c`:
  - `backport-6.18/787-v7.5-net-phy-realtek-return-MDIO-read-errors-from-hwmon.patch`
    (upstream `d5b5ab50d2f6`, v7.5): **recommended backport candidate** for
    Linux 7.3. `CONFIG_REALTEK_PHY=m` and `CONFIG_REALTEK_PHY_HWMON=y` are
    enabled on x86/64; without it, failed MDIO reads in `rtl822x_hwmon_read()`
    are masked/shifted into bogus temperatures instead of returning the error.
    Absent from 7.3.5 and applies with zero fuzz and zero offsets.
  - `pending-6.18/744-net-phy-realtek-register-hwmon-thermal-zone.patch`:
    **optional parity candidate** only. Registers `HWMON_C_REGISTER_TZ` for
    device-tree thermal zones alongside carried `742`/`743`; applies cleanly
    after `787` with zero fuzz/offsets, but is a no-op on ACPI x86/64 because
    `drivers/hwmon/hwmon.c` gates it on `hdev->of_node` and `CONFIG_THERMAL_OF`.
  - `target/linux/generic/config-6.18` removed `CONFIG_ARCH_FORCE_MAX_ORDER=11`
    (`4a90fed434`); `config-7.3` still carries it as a no-op on x86/64
    (optional config hygiene sync).
- **Full 6.18 / 7.3 audit**: This check leaves the 7.3 patch stack and
  `configs/mainline-kernel-patches.json` unchanged pending backport
  authorization. All **355 carried Linux 7.3 patches** match their registered
  SHA-256 hashes and apply with `--fuzz=0` to a fresh extraction of verified
  Linux `7.3.5` plus current generic/x86 overlays. The optional MAP-E tunnel
  finding remains open.

### Realtek PHY hwmon backports completed, 2026-11-20

The authorized follow-up carries both `787` (`backport-7.3/`) and `744`
(`pending-7.3/`) byte-identically from 6.18, removes
`CONFIG_ARCH_FORCE_MAX_ORDER=11` from `target/linux/generic/config-7.3`, and
updates `configs/mainline-kernel-patches.json` (registering both ports and
marking the 6 upstream-dropped `6.18.61-6.18.64` backports with `removed_in`).
All **357 carried Linux 7.3 patches** match their registered SHA-256 hashes and
apply with `--fuzz=0` to a fresh extraction of verified Linux `7.3.5` plus
current overlays; `scripts/checkpatch.pl` reports 0 errors / 0 warnings on both
patches, and the resulting patched `drivers/net/phy/realtek/realtek_hwmon.c`
compiles cleanly against the selected x86/64 kernel headers in isolation. No
full kernel or generation rebuild was performed.

## Upstream synchronization review, 2026-11-21

Merged OpenWrt through `e7f788a9c1` (five incoming main-tree commits) as
`3ced84a7dc`, plus three LuCI and three Passwall packages commits. The other
feeds were already current. All merges completed without conflicts and retain
their previous local HEADs.

- **Mainline Linux 7.3**: `update-mainline-kernel.py --check` reports 7.3.5 is
  current. No incoming generic or x86 6.18 files changed, so no new native 7.3
  backport is needed. All 357 carried patches apply with zero fuzz to the
  SHA-256-verified 7.3.5 archive. The incoming mac80211 AP-VLAN fix remains in
  its separate backports package and prepares successfully.
- **Custom packages**: all 188 entries pass the updater: 147 current, 36 local
  and five intentional review pins. No custom recipe or Argon update is
  available.
- **Validation**: feed update/install, nine nonempty indexes, generated-link
  checks, strict isolated Kconfig, 109 focused Python tests and two local LuCI
  JavaScript tests pass. No selected Kconfig option changes; the working
  `.config` and all original local repository states are preserved.

This was a source-only synchronization. No full build, VM test, publication,
Git push, router deployment, restart or reboot was performed.

### Upstream follow-up through `6bd48701eff9`, 2026-11-21

Merged 17 main-tree commits as `47d93490b2`, 29 packages-feed commits as
`18cf20a1b`, and three LuCI commits as `fde0243793`. The other six Git feeds
were current. The custom updater checked all 188 entries (147 current, 36
local, five review pins) and made no recipe or Argon update.

OpenWrt commit `6dcd4886b389` adds the only new patch in the generic/x86
6.18 stacks, `pending-6.18/550-drm-amd-display-fix-frame-size-warning.patch`.
It applies to patched Linux 7.3.5 with zero fuzz and a four-line offset. It
adds per-object frame-warning flags to seven AMDGPU display objects for
GCC 15 on x86/generic with `CONFIG_FRAME_WARN=1024`. The selected x86/64
kernel has `CONFIG_DRM_AMDGPU` disabled and `CONFIG_FRAME_WARN=2048`. No
backport is needed for this configuration. Reassess if AMDGPU display is
enabled with a lower frame-warning threshold.

Kernel.org still lists 7.3.5 as the latest final release. All 357 carried
patches match their registered hashes and apply with zero fuzz to the
verified archive. The 6.18 registry audit records the new AMDGPU patch
alongside the four previously reviewed unregistered patches and 60
existing source-hash differences.

The Netfilter split adds `kmod-nf-xtables` to the working, desktop and router
profiles. Strict Kconfig preserves every previous selection, and the kernel
module mapping and legacy `kmod-iptables` dependency chain were checked.
Preserved the kmod basename behavior using kmod 34.3's implementation and
verified it with a disposable depmod and modprobe fixture. The kmod,
nginx, iperf3 and mbedTLS package builds and APK signature checks passed.
mbedTLS uses release 3 because release 2 is reserved by the migration ledger.
Feed indexes, package links and original repository state were checked.
Evidence is under `.git/pull-preserve/20261121T135536Z/`.

### AMDGPU frame-warning backport

Carried OpenWrt's `550-drm-amd-display-fix-frame-size-warning.patch` byte for
byte into `pending-7.3/` and registered both hashes. The patch lets seven
display objects use Linux 7.3's existing per-object frame-warning limit while
preserving the kernel-wide setting. All 358 patches match the registry and
apply with zero fuzz to the SHA-256-verified Linux 7.3.5 source.

Built all seven objects through the AMDGPU Kbuild rules using GCC 15.3 in
an isolated x86/64 configuration with AMDGPU display enabled,
`CONFIG_WERROR=y` and `CONFIG_FRAME_WARN=1024`. Each compile used the
3072-byte AMDGPU override after the 1024-byte global flag. Validation
covered object compilation without a full driver link or hardware test.

## Upstream synchronization and Linux 7.3.6 update, 2026-11-24

Merged OpenWrt through `ce245c8739` (11 incoming main-tree commits) as
`f2f9d5cd84`, plus 1 `luci` (`4e067c2e51`), 5 `packages` (`5b68c6ddf`), 4
`passwall_luci` (`21a1b9fc`, preserving the local `luci.mk` Git revision
versioning in `luci-app-passwall/Makefile`), and 3 `passwall_packages`
(`30edd77`) commits. The `routing`, `taskplan`, `telephony`, and `video` feeds
had no incoming commits. Backup branches are `backup/pre-upstream-20261124T041713Z`
across the main repository, all eight Git feeds, and `package/custom/luci-theme-argon`.

- **Mainline Linux 7.3 -> 7.3.6**: Updated `target/linux/generic/kernel-7.3`
  from `7.3.5` to `7.3.6` (SHA-256
  `8183d475a76a0faffa92d6cd500af421f589dfd0300a0f1060bb875e11d45723`):
  - Dropped `target/linux/generic/backport-7.3/706-04-v7.3-netfilter-flowtable-use-the-vlan-id-not-the-full-tci.patch`
    (absorbed verbatim in Linux `7.3.6`; reverse-applies cleanly with zero fuzz)
    and marked it `upstream` in `configs/mainline-kernel-patches.json`.
  - Dropped `target/linux/generic/pending-7.3/880-leds-st1202-add-hardware-accelerated-blink-support.patch`
    (absorbed upstream in Linux `7.3.6` with phase-shift and `max_brightness`
    updates) and marked it `upstream` in `configs/mainline-kernel-patches.json`.
  - Refreshed `target/linux/generic/hack-7.3/904-debloat_dma_buf.patch` for
    Linux `7.3.6`'s removal of `select GENERIC_ALLOCATOR` in `net/Kconfig`
    and `target/linux/generic/hack-7.3/940-kbuild-extract-modules-builtin-modinfo-from-vmlinux_o.patch`
    for `7.3.6`'s simplified `cmd_modules_builtin_modinfo` context in
    `scripts/Makefile.vmlinux`, updating both `ported_sha256` entries.
  - All **356 remaining carried Linux 7.3 patches** (352 registered ports plus
    4 local x86/7.3-only patches) match their registered hashes and apply with
    `--fuzz=0` to the verified Linux `7.3.6` archive via both
    `scripts/update-mainline-kernel.py --update` and `make target/linux/prepare`.
  - Diffed all Kconfig files between `7.3.5` and `7.3.6` and ran
    `make ARCH=x86_64 listnewconfig` against the merged x86/64 `config-7.3`;
    no new x86/64 kernel Kconfig symbols or prompts were introduced (`7.3.6`
    adds `DRM_AMD_DC_DCE` under disabled `DRM_AMD_DC` and 32-bit-only
    `RTC_HCTOSYS_TIME32_LIMIT`, and converts unused `SERIAL_8250_HUB6` from
    `tristate` to `bool`).
- **Incoming 6.18 patches**: Zero files under `target/linux/generic/` or
  `target/linux/x86/` were added, modified, or removed. Incoming kernel patches
  are target-specific (`ipq806x` `stmmac` fixes with `CONFIG_STMMAC_ETH` unset
  on x86/64, `rockchip` NanoPi R2S Plus DTS, `sunxi` `dwmac-sun8i` reset fix,
  plus `airoha`/`ath79`/`bcm47xx` updates). No new 6.18 generic/x86 patch
  requires backporting to Linux `7.3`. The full 583-patch generic/x86 6.18
  audit matches the prior baseline (four previously reviewed non-x86
  unregistered entries and 60 prior `6.18.61-6.18.64` context refreshes). The
  optional MAP-E tunnel finding remains open.
- **Custom packages**: Updated `gnome-control-center` (`51.1` -> `51.2.1`),
  `google-chrome-bin` (`158.0.8127.36` -> `158.0.8127.88`), `mozjs140`
  (`140.15.0` -> `140.17.0`; `rebuild_dependents: gjs`), `nautilus`
  (`51.1` -> `51.2`), and `luci-theme-argon` (merged upstream `076355f` and
  bumped `PKG_RELEASE` to `20261124`). Verified `make package/custom/<pkg>/prepare`
  for `gnome-control-center`, `nautilus`, and `mozjs140`; all local patches
  applied cleanly.
- **Validation**: Regenerated all nine nonempty feed indexes, removed three
  stale broken `package/feeds/packages/` symlinks (`dvtm`, `netcat`, `siit`),
  passed isolated strict `conf --fatalrecursive --olddefconfig` with zero
  selected-option changes (only unset `brcmsmac` entries removed), and passed
  351 host Python unit tests across 11 suites plus 3 LuCI JS view tests.
- **Build and publication (generation 87)**: Built Linux `7.3.6` generation
  `87` (`linux-image-7.3.6-87-openwrt`, kernel ABI
  `7.3.6~5eaacd40bf4a752328abbcfbf2b75c1e-r1`), allocated effective rebuild
  releases for the nine kernel-dependent executables re-linked against glibc
  2.44 `crt1.o` (`grub2-bios-setup` / `grub2-editenv` `2.12-r10`, `mtd`
  `29-r4`, `ip-full` / `nstat` / `ss` / `tc-tiny` `7.3.0-r3`, `strace`
  `6.18-r6`, `fuse-utils` `2.9.9-r6`), decoupled `router-audit` (`1.0.0-r8`)
  from `docs/router-audit.md`, passed the coordinated router upgrade preflight
  (1,605 packages, 3,312 ELF files), and published userspace snapshot
  `20261124T051930.960788Z` and kernel snapshot `1795497048275680482`. VM not
  run: routine Linux `7.3.5` -> `7.3.6` stable point release and compatible
  package updates with no major behavior change or new functionality. No router
  package installation or reboot was performed.
