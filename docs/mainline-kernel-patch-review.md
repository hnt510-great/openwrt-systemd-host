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
