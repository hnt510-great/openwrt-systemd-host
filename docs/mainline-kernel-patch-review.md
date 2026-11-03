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
