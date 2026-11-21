# Incremental build and publication acceleration plan

**Status: design and exploration complete on 2026-11-21; implementation is delegated
to another agent. No acceleration changes from this plan have been implemented yet.**

This is the implementation handoff for accelerating routine retained-tree
`./scripts/build-and-publish.sh -j16` runs. It combines the approved plan with the
measured build/publication evidence and the non-obvious constraints found during
exploration.

Related records:

- [base-files immutable version fix and validation](base-files-version-validation.md)
- [LAN APK publisher and allocation mechanisms](lan-apk-feeds.md)
- [existing LZ4/pigz image acceleration](squashfs-lz4-validation.md)
- [publication readiness requirements](publication-readiness.md)
- [APK upgrade preflight](apk-upgrade-preflight.md)

## 1. Executive summary

The final successful run took **711.590s**, but it is **not a valid no-op baseline**.
Its 652.706s make phase included `package/cleanup` and regenerated **1,227 APK
payloads** while only 16 build stamps changed. A true warm no-op must be measured
before changing cleanup, kernel-bundle or image dependencies.

The safest concrete opportunities, in priority order, are:

1. **Use `NO_DEPS=1` only for allocation retries after a successful full world
   build.** The observed ledger-triggered base-files retry took 296.846s and
   regenerated 171 APKs; a later warm direct build took 22s. Standalone
   publication-only allocation must retain dependencies.
2. **Measure, then accelerate existing rootfs-cache copies with Btrfs reflinks.**
   The approximately 5.9 GiB cache is currently copied with full `cp -a` operations
   on both restore and save. Preserve independent CoW files; never hardlink mutable
   roots.
3. **Use the existing `cp_if_changed` helper for final image/artifact copies.** This
   avoids rewriting identical multi-GiB outputs and preserves their mtimes.
4. **Reject same-version APKs before expensive ucode/ELF validation.** The candidate
   is already invalid after manifest/index checks; this saves about 28s on rejected
   attempts without removing any check from viable publications.
5. **Batch remaining per-package APK metadata classification reads.** This is a
   smaller, low-risk subprocess-overhead improvement.
6. **Instrument ucode/ELF subphases before combining or parallelizing them.** Do not
   start with the more invasive validator rewrite.

The completed base-files version fix is already a major avoidance win: for ordinary
local commits it removes the observed **39.159s rejected publication + 296.846s
allocation retry = 336.005s** path. Keep that fix intact.

## 2. Confirmed scope and non-negotiable constraints

The user selected the following scope:

- Optimize **routine incremental builds**, retaining `build_dir/` and `staging_dir/`.
- Prefer in-process reuse and existing caches; **do not add a new cross-build
  persistent APK/ELF scan cache**.
- Keep `-j16`; the Ryzen 7 5700X3D host has 8 physical/16 logical CPUs and 31 GiB
  RAM. Increasing jobs is likely to increase memory/I/O contention, not throughput.
- Implementation is to be performed by another agent, using this document as the
  handoff.

Do not weaken any of these invariants:

- Published APK identities are immutable; changed bytes require a new version.
- Kernel generations and their input/timestamp checks remain reproducible.
- APK signatures, architecture, kernel pins, ucode ABI and ELF ABI are fully checked.
- Staged snapshots are freshly hashed at the documented authorization and promotion
  boundaries.
- Both router upgrade paths are simulated, and the router baseline is rechecked
  before promotion.
- Userspace is promoted before the kernel commit pointer, with rollback behavior
  preserved.
- Publication never installs on the physical router.
- Do not reinstall disabled scheduled maintenance or run feeds updates as part of
  this performance work.

A future production publication requires explicit user authorization. Unit and
integration tests should use temporary destinations. Do not deliberately corrupt a
production package merely to benchmark allocation or rejection paths.

## 3. Starting state for the implementation agent

### Source and artifacts

- HEAD at the time of analysis: `5474fdb95c` (`image: accelerate x86_64 rolling
  image packaging`). Check the live tree before starting.
- Current published kernel generation: `7.3.5-79-openwrt`.
- Current published userspace snapshot from the final measured run:
  `/srv/openwrt-feeds/public/snapshots/20261121T003238.701506Z`
- Reference image:
  `bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz`
  - 1,352,481,148 bytes
  - SHA-256 `579aa7924c8714418c207cc63f879bb64315a47b00cf51649a4bc8eefa1c52fa`
- Reference APK: `base-files-1769.20.73443~5474fdb95c.apk`
  - SHA-256 `f8a667bded737f56390b8b3fb276ff630f2c741b38db5133bed1ff48613c84bb`

### Existing working-tree changes: preserve them

The base-files fix is present but uncommitted. The following are intentional and
must not be overwritten or reverted:

- `package/base-files/Makefile`: adds checkout-wide commit count and actual HEAD to
  the APK identity, and writes effective `VERSION` to `base-files.version`.
- `configs/apk-elf-rebuilds.mk`: contains three new lines allocating the already
  published historical `1769.20~e7f788a9c1-r1` identity. Keep this entry.
- `scripts/allocate-rebuild-releases.py`: comment clarification only.
- `scripts/tests/test-apk-source-versions.py`: base-files version regression tests.
- `docs/lan-apk-feeds.md` and `docs/base-files-version-validation.md`: fix guide and
  validation record.

Also leave unrelated existing items alone, including the argon submodule state,
`package/custom/fastfetch/.claude/`, and `package/luci-app-argon-config/`.
Preserve the working `.config`; do not replace it with the tracked snapshot.

The acceleration targets `scripts/build-and-publish.py`, `package/Makefile`,
`include/image.mk`, and `scripts/publish-lan-apk-feeds.py` had no acceleration edits
at handoff time.

### Existing test state

- Four focused base-files/Passwall source-version tests pass.
- All 16 allocator tests pass.
- The complete `test-apk-source-versions.py` currently reports **17 errors** in the
  unchanged recipe-release guard for existing feed/ledger reservations (ppp, nginx,
  ffmpeg and others). Record this baseline; do not attribute those errors to the
  acceleration work or silently hide them.
- `git diff --check` passes for the base-files fix.

## 4. Measured workflow evidence

### Four workflow attempts

| Run | Main make | Other/retry work | Publication | Total/result |
| --- | ---: | --- | ---: | --- |
| Initial | 496.571s | `prepare-tmpinfo` 3.190s; generation 0.909s | Not reached | 500.778s; util-linux parallel build failed |
| Retry | 537.984s | `prepare-tmpinfo` 0.310s; generation 0.855s | 80.849s; stopped in userspace preparation | 621.052s; base-files same-version rejection |
| Automatic allocation | 324.835s | failed publication 39.159s; targeted retry 296.846s | 55.562s successful retry | 720.248s; generation 79 published |
| Fixed base-files | 652.706s | `prepare-tmpinfo` 1.557s; generation 0.996s | 55.395s | 711.590s; successful, no allocation |

A standalone verbose `make package/base-files/compile -j1 V=s` after the initial
parallel util-linux failure succeeded in 8.93s. The later direct base-files build
used `-j16`, took 22s end to end, and its own base-files compile record was 2.43s.

### Why the final 652.706s make was atypical

The final log uniquely included `make[2] package/cleanup`.
`package/Makefile` implements this by removing `STAGING_DIR_ROOT`. The run then
regenerated 1,227 APKs and 1,227 `.pkgdir/*.installed` payloads; only 16 `.built*`
files, including check companions, changed. Most time was packaging/staging, not
source recompilation.

| Final make phase | Seconds |
| --- | ---: |
| Initial work and `package/cleanup` | 5.093 |
| `target/compile` | 110.695 |
| `package/compile` | 250.040 |
| `package/install` | 130.867 |
| `target/install` | 139.756 |
| Index/metadata/checksum tail | 16.255 |
| **Total** | **652.706** |

Do not remove cleanup based on this run. If a later true no-op still rebuilds many
payloads, identify the exact invalidation first. Manifest-aware stale-file removal
is a separate, higher-risk design.

### Final publication profile

| Phase | Seconds |
| --- | ---: |
| Read and stage APKs | 9.768 |
| Read router baseline/check trackers | 2.037 |
| Prepare userspace feeds | 29.664 |
| Prepare kernel feed | 1.308 |
| Record snapshot hashes | 1.791 |
| Simulate router upgrade | 5.563 |
| Verify userspace + kernel snapshots | 1.714 |
| Recheck router | 1.766 |
| Save receipt | 0.006 |
| Promote userspace + kernel | 1.721 |
| Clean staging | 0.053 |
| Other near-zero transitions | 0.004 |
| **Publication total** | **55.395** |

The successful run changed only target/base-files but examined approximately 1,405
source APKs and produced a 3,485-package, approximately 2.52 GiB projection. Its ELF
audit covered 1,131 newest packages and 520 migration alternatives; 1,130 of the
1,131 newest identities were unchanged. This makes cross-build caching attractive,
but that option was explicitly excluded for this pass.

Router baseline + simulation + recheck totaled only **9.366s**. Do not prioritize
router micro-optimization over local build/APK work.

## 5. Non-obvious root causes and existing acceleration

### 5.1 Base-files identity failure is already fixed

Formerly, base-files embedded the full revision/build timestamp while its APK version
used only package-local `COMMITCOUNT` and the upstream merge-base hash. Local commits
could change signed bytes without changing the package version.

The current fix uses a form such as `1769.20.73443~5474fdb95c`, with checkout-wide
commit count and actual HEAD. It also makes the rootfs version lock use effective
`VERSION`, including historical ELF mappings. Same-commit retries remain stable;
dirty uncommitted payload changes still require explicit allocation/version handling.

Do not revert this to solve performance. The final production run needed no
allocation and published the new base-files APK successfully.

### 5.2 The ledger globally invalidates package payloads

`configs/apk-elf-rebuilds.mk` is a prerequisite of package payload/APK rules in
`include/package-pack.mk`. An allocation retry edits that ledger before calling an
explicit package target. The observed base-files allocation retry consequently
regenerated:

- 171 APKs total: 80 userspace and 91 target APKs, including 81 kmods;
- 345 pkginfo files;
- 296.846s of work.

The later 22s direct build benefited from those outputs already being fresh. The
first implementation should constrain dependency traversal, not remove the ledger
prerequisites. Legitimate ledger changes can alter package versions and exact
dependency metadata; selective ledger invalidation requires a separate reverse-
dependency design and proof.

### 5.3 Retained-tree and image acceleration already exist

- `CONFIG_AUTOREBUILD=y`, `CONFIG_AUTOREMOVE` is off; package/host stamps and retained
  build directories are reused.
- Jobserver tokens propagate through top-level/package/host/Ninja rules. Heavy desktop
  recipes generally opt into parallel builds, with per-package opt-outs retained.
- Package metadata/target scans, config synchronization, diffconfig, merge and index
  operations already have timestamp/content no-op handling.
- The rootfs cache keys on merged package indexes, install list, complete `.config`,
  epoch, host tools, rootfs rules and `files/`; it restores both `root` and
  `root.orig`. The cache location is
  `build_dir/target-x86_64_glibc/rootfs-cache-x86-systemd` and occupied about 5.9 GiB.
- Commit `5474fdb95c` enables LZ4 for normal/installer squashfs, direct pigz `-1 -n
  -p8` for combined systemd images, and removes redundant x86_64 rootfs-only images.
  Validation measured normal squashfs **99.25s -> 1.33s** median and outer combined
  compression **85.96s -> 8.71s**. Keep pigz at eight threads; sixteen were not
  faster.
- The old deterministic compression cache is not an opportunity here: a measured
  cache hit took 25.32s versus 8.74s for direct pigz. Do not reintroduce it without
  new evidence.
- Download reuse through `dl/` and cargo caches is active, but clean/download work is
  outside the selected incremental scope.

### 5.4 Disabled features that are not first-line no-op optimizations

- `CONFIG_CCACHE` is off. The existing integration covers target/host/CMake/kernel
  compiler paths, but ccache cannot accelerate a true retained-tree no-op. It is not
  part of this plan.
- `CONFIG_RUST_SCCACHE` is off. Enabling it alone is unsafe for the current feed-
  provided Rust setup because the expected staged/system wrapper is not available.
- Autoconf result-cache infrastructure exists under `tmp/configure-cache`, but target
  packages must opt in individually. Blanket opt-in is incorrect for configure
  scripts with side effects inside cache checks.
- Mold could help link-heavy edit/rebuild cycles, but gives no no-op benefit and needs
  full-image validation. LTO/GC-sections are not build-time acceleration shortcuts.
- The installer constructs a separate clean rootfs/component repository. It cannot
  simply reuse the normal rootfs cache.
- Do not remove image/kernel `FORCE` dependencies casually. Correct no-op skipping
  would need keys covering image-affecting config, scripts, host tools, signing keys,
  package indexes and epochs.

## 6. Implementation plan

### Phase 0: accounting and a real warm baseline

1. Reuse the read-only timing approach in `tmp/time-build-and-publish.py`. It calls
   the production workflow, times `run_make`/generation/publication, and enables the
   existing publication progress callbacks. Preserve stdout JSON and make arguments.
2. Prefer the existing **`BUILD_TIME_LOG`** instrumentation over permanent `V=s`:

   ```sh
   # Build-only baseline: no feed publication.
   BUILD_TIME_LOG=/absolute/new/run.events python3 scripts/build-and-publish.py build-only -j16
   scripts/build-time-report.pl -n 30 /absolute/new/run.events
   ```

   `rules.mk` already emits prepare/configure/compile/install begin/end events, and
   `build-time-report.pl` reports wall share, solo time, mean parallelism and idle
   time. Use a new log per run because the event writer appends.
3. Set `BUILD_TIME_LOG` through the environment. Do not add arbitrary command-line
   `CONFIG_*` assignments to the benchmark: `kernel-build-inputs.py` fingerprints
   make command-line assignments and could reserve a new generation.
4. Add optional phase wrappers for rootfs cache restore/save, final image copies, APK
   hashing/copying, classification, index generation/signing, ucode validation, ELF
   extraction and ELF record validation. If timing is moved into
   `build-and-publish.py`, make it opt-in and leave normal output/artifacts unchanged.
5. If packaging remains conflated with compile, add `BUILD_TIME_LOG`-guarded pack
   begin/end events around `BuildTarget/ipkg` in `include/package-pack.mk`. Touching
   that file invalidates packages, so perform a new settling run before benchmarking.
6. After any Makefile/ledger change, run one settling full-world build. Then run at
   least **three consecutive identical warm builds**, recording every result and
   outliers. Use the same checkout, `.config`, `-j16`, retained directories and
   kernel timestamp state.
7. Define warm no-op behavior explicitly. Build-only runs cover compilation/rootfs;
   snapshot/alias assertions require a separately authorized full workflow or an
   isolated publisher fixture:
   - no new kernel generation;
   - zero regenerated APK payloads;
   - no new userspace/kernel snapshots;
   - unchanged aliases;
   - unchanged APK/image bytes.

If these conditions fail, fix or document the invalidation before claiming a copy or
compiler optimization improved no-op performance.

### Phase 1: constrain allocation retries

Modify `scripts/build-and-publish.py`:

1. Add `dependencies_ready=False` (or equivalent) to `publish_allocating()`.
2. `build()` passes true only after its full-world `run_make()` has succeeded in the
   same invocation. A targeted build or failed world build does not qualify.
3. When true, allocator-triggered `ALLOCATE.rebuild_targets()` calls add
   `NO_DEPS=1`, while retaining `make_options()` job/verbosity propagation.
4. Standalone publish-only `--allocate-rebuilds` retains normal dependencies.
5. Keep all allocation rounds, full subsequent publication checks and failure
   behavior. `include/subdir.mk` already implements `NO_DEPS`; do not duplicate that
   mechanism or remove global ledger prerequisites.

Tests in `test-allocate-rebuild-releases.py` and `test-build-and-publish.py` must
prove both the presence and absence of `NO_DEPS=1`, bounded retry rounds, unchanged
stdout/timing behavior, and no use after a failed/targeted world build.

Expected result: reduce the observed 296.846s retry toward the warm direct-build
scale of about 22s. Treat this as a hypothesis to measure in an isolated fixture,
not a guaranteed production number.

### Phase 2: reduce copy I/O after measuring it

#### Rootfs cache CoW copies

Modify only the four cache save/restore copies in `package/Makefile`:

- two copies in `rootfs_cache_restore`;
- two cache-save copies in `apk_install_rootfs`.

Use `cp -a --reflink=auto` on this Btrfs host, retaining normal copy fallback. Do not
change `rootfs_cache_key`, cache location, installer clean-rootfs logic, or global
`CP`. Do not use hardlinks between mutable roots and the cache.

Required integration checks:

- writes in a restored root never alter cached content;
- writes in the source root after cache save never alter cached content;
- no cross-tree hardlinks are introduced;
- modes, ownership, symlinks, hardlinks **within** each tree, xattrs and capabilities
  survive;
- cache-hit and cache-miss builds produce byte-identical APKs/images;
- non-CoW fallback has identical semantics.

The first build after editing `package/Makefile` may intentionally miss because the
Makefile is part of `rootfs_cache_key`. Benchmark a subsequent warm run.

#### Final artifact copies

In `include/image.mk`, replace the final initramfs, kernel, image and artifact
`cp $$^ $$@` operations with the existing `cp_if_changed` helper from `rules.mk`.
Cover destination-missing, identical-content and changed-content cases. Identical
outputs must retain inode/mtime; changed bytes must still replace the destination.
Compare final hashes. Do not change image generation or compression rules.

### Phase 3: publication fast paths with unchanged safety gates

Modify `scripts/publish-lan-apk-feeds.py`:

1. Move `same_version_rebuild_error()` after all repositories have been scanned and
   after existing architecture, kernel ABI, kernel-pin, index and retained-package
   checks, but before `validate_ucode_abi()` and `validate_elf_abi()` when
   `same_version_rebuilds` is non-empty.
2. Preserve aggregate diagnostics for every same-version candidate, including ucode
   and ordinary packages. Valid changes must still execute both validators and all
   signature checks. No snapshot or alias may move on rejection.
3. Replace per-file `dump_index()` calls used for kernel/userspace classification with
   a bounded `dump_indexes()` prepass and a path-to-metadata map. Preserve source
   order, duplicate handling, first-error behavior and kernel/userspace decisions.
4. Leave kernel-channel restructuring out of the first batch: preparation measured
   only 1.308s.
5. Keep every staged-source hash, changed-file destination hash, snapshot
   authorization hash, router simulation/recheck and promotion hash unchanged.

Tests in `test-lan-apk-publisher.py` should mock the validators to prove they are not
entered for an already rejected identity and are entered for valid changes. Retain
same-version aggregation, ucode mismatch, retained-consumer, malformed inventory,
rollback and alias tests. Exercise classification across batch boundaries and mixed
userspace/kmod/kernel-owned names.

Expected result: approximately 28s saved on rejected userspace preparations, plus a
small classification improvement. Successful full-validation savings are not claimed
without subphase measurements.

### Phase 4: optional safe metadata reuse, only if profiling justifies it

A safe follow-up can reuse **decoded metadata**, not verification freshness:

1. `project()` may populate a publication-local map from exact staged path to
   `(verified_copy_digest, decoded_metadata)`; `copy_package()` already computes the
   verified copy digest.
2. `LAN.publish()` must still freshly hash **every staged APK**, exactly as now.
3. Require the fresh digest to equal the mapped verified digest before using cached
   metadata. Any mismatch fails before classification or the unchanged early return.
4. Unmapped standalone/artifact paths use the existing or newly batched decoder.
5. Keep this map in the one locked process; do not persist it across builds.

Do not simply reuse old staging hashes at the current source-scan point. That would
miss post-staging mutation of unchanged APKs before the unchanged early return.
If this freshness-preserving design is not implemented, omit metadata reuse entirely.

### Phase 5: defer invasive validator and router changes

Exploration found these future opportunities, but they are measurement-gated and not
part of the first implementation batch:

- ucode and ELF currently select newest packages separately and issue separate APK
  version-comparison subprocesses;
- the 17 checked ucode packages can be extracted once by ucode and again by ELF;
- newest-record `ELF.validate()` is serial, while migration alternatives already use
  the bounded `forked_map()` helper;
- each of 520 alternatives constructs a full ELF context, but inherited RPATH state
  makes naive context sharing unsafe;
- userspace/kernel hashes could be computed with bounded parallelism while still
  independently reading and comparing every file;
- publication-scoped SSH multiplexing could reduce connection setup, but every call
  must still run a fresh remote capture/solver process.

Before any combined/parallel validator implementation, record separate extraction and
CPU costs. Preserve per-record context semantics, sorted aggregated errors, native
ucode fixtures, migration alternatives and worker failure ordering. Do not remove or
cache the documented preflight/authorization/promotion hashes.

## 7. Verification and adoption protocol

### Focused checks

Run the narrowest relevant suites after each independent change:

```sh
python3 scripts/tests/test-allocate-rebuild-releases.py
python3 scripts/tests/test-build-and-publish.py
python3 scripts/tests/test-lan-apk-publisher.py
python3 scripts/tests/test-elf-abi.py
python3 scripts/tests/test-ucode-abi.py
python3 scripts/tests/test-apk-upgrade-preflight.py
python3 scripts/tests/test-apk-source-versions.py
sh scripts/tests/test-alternatives.sh
git diff --check
```

The complete source-version suite has the 17 pre-existing errors documented above;
compare exact results rather than claiming a clean suite. Add focused CoW and
`cp_if_changed` integration checks for the respective Makefile changes.

### Benchmark scenarios

Measure these separately; do not combine their timings into a single claimed saving:

1. true unchanged-input no-op;
2. one ordinary package with a proper release bump;
3. same-version rejection in a temporary destination;
4. allocation retry after a successful full world in an isolated fixture.

For each change:

1. use the same host, source content, config, arguments, retained directories, router
   state and kernel timestamp state;
2. perform one settling run, then at least three warm runs;
3. compare medians and ranges, and adopt the change only when improvement exceeds
   observed run-to-run variation;
4. compare APK/image hashes, ABI, generation, snapshot sets, aliases and receipts,
   normalizing only documented snapshot/receipt timestamps and timing records;
5. retain all mutation, rollback and userspace-before-kernel tests.

No VM is required while outputs remain byte-identical and no runtime behavior changes.
An unexpected image/package difference must be diagnosed before publication, not
bypassed. Major/runtime changes need their relevant VM validation.

### Final documentation and publication

- Record actual before/after results, image/APK hashes, test counts, scope and external
  evidence in a new hand-written
  `docs/incremental-build-acceleration-validation.md` when implementation occurs.
- Link the guide/plan and validation record together.
- Do not commit or push unless the user explicitly asks.
- Do not production-publish without explicit user authorization for that run.
- Publication itself must never install on the physical router.

## 8. Critical file map

| Path | Relevant responsibility |
| --- | --- |
| `scripts/build-and-publish.py` | `build`, `run_make`, `project`, `publish_locked`, `publish_allocating`, `make_options` |
| `scripts/publish-lan-apk-feeds.py` | `dump_index`/`dump_indexes`, source classification, manifest scan, ucode/ELF gates, `forked_map` |
| `scripts/apk-upgrade-preflight.py` | router capture/simulation, prepared snapshot hashes, authorization and promotion safety; keep boundaries intact |
| `scripts/kernel-build-inputs.py` | kernel-generation fingerprinting, including make command-line assignments |
| `scripts/allocate-rebuild-releases.py` | allocation plan/apply and explicit rebuild targets |
| `include/subdir.mk` | existing `NO_DEPS`, package logging and jobserver-aware submake behavior |
| `include/package-pack.mk` | payload/APK prerequisites and optional pack timing; global ledger mtime currently invalidates packages |
| `package/Makefile` | cleanup, merge/index no-op handling, rootfs cache key/install/restore/save |
| `include/image.mk` | final initramfs/kernel/image/artifact copies; retain generation dependencies |
| `rules.mk` | `cp_if_changed`, `BUILD_TIME_LOG`, compiler/cache configuration |
| `scripts/time.pl` | per-submake CPU/wall records |
| `scripts/build-time-report.pl` | wall-share/solo-time/parallelism report for `BUILD_TIME_LOG` |
| `scripts/tests/test-{build-and-publish,allocate-rebuild-releases,lan-apk-publisher,elf-abi,ucode-abi,apk-upgrade-preflight}.py` | focused regression coverage |

## 9. Evidence locations

The base-files investigation evidence is preserved outside the repository at:

`/srv/openwrt-validation/base-files-version-validation-20261121-nE1YLL/`

It includes:

- `build-publish-same-version.log`: the base-files immutable-version rejection;
- `build-publish-allocated.log`: automatic allocation and the 296.846s retry;
- `build-publish-fixed.log`: final successful 711.590s workflow;
- `base-files-build.log`: verbose direct base-files build;
- focused/full test output and `SHA256SUMS`.

Existing LZ4/pigz evidence is under:

`/srv/openwrt-validation/squashfs-lz4-validation-20261121/`

The temporary timing wrapper is `tmp/time-build-and-publish.py`. It is an ignored
measurement aid, not a tracked production interface. Any permanent timing interface
must be opt-in, tested and documented rather than exposing the temporary wrapper as
an API.

## 10. Implementation handoff checklist

- [ ] Read `CLAUDE.md`, this plan and the current diffs before editing.
- [ ] Confirm the live HEAD, working tree, `.config`, generation and published state.
- [ ] Preserve the base-files fix, historical ledger entry and unrelated user files.
- [ ] Establish settling + three warm baselines with `BUILD_TIME_LOG` and phase timing.
- [ ] Implement and test `dependencies_ready`/`NO_DEPS=1` gating independently.
- [ ] Measure copy costs before adding reflink/`cp_if_changed`; prove output and CoW independence.
- [ ] Implement same-version fail-fast and batched classification with validator/mutation tests.
- [ ] Keep staging, snapshot and router verification fresh; no persistent scan cache.
- [ ] Record all results, including pre-existing failures and outliers.
- [ ] Obtain explicit authorization before any production publication; never install on the router.
