# Same-Version APK Rebuild Diagnosis & Release Allocation

Published APK identities (`name`, `version`, `arch`) are immutable. When a
rebuild produces different APK bytes under an already-published version, the
LAN publisher rejects it with `SameVersionRebuildError` instead of overwriting
the published package.

This workflow explains **what changed**, **what can be proven**, and **which
release action is safe**, without requiring manual edits to
`configs/apk-elf-rebuilds.mk` for routine cases.

Related docs: [local LAN APK feeds](lan-apk-feeds.md),
[shared-library ABI upgrades](elf-abi-upgrades.md),
[validation record](apk-rebuild-release-validation.md), and the
[implementation handoff](apk-rebuild-release-handoff.md).

## 1. Decision Model & Action Priority

`scripts/diagnose-apk-rebuild.py` (`ANALYZER_VERSION=2.1`,
`POLICY_VERSION=phase2-evidence-v1`) evaluates every difference across APK
framing, complete ADB metadata, file contents, ELF dynamic contracts,
out-of-APK type ABI evidence, and isolated cold rebuild results. All findings
are retained in the report; mixed `unknown` + `change` (or `unknown` +
`so_changed`) never bypasses review.

| Priority | Action | When selected |
|---|---|---|
| 1 | `keep_existing` | Whole-APK bytes are identical. |
| 2 | `reject` | Enforced signature verification fails, ELF header/type ABI is incompatible (`type_abi_incompatible`), or isolated cold rebuild drifts under identical inputs (`cold_rebuild_payload_drift`). |
| 3 | `reuse_published` | Both APKs verify under trusted keys and decompress cleanly to the exact same complete `ADB.` stream (pure outer `ADBd` DEFLATE re-encoding). |
| 4 | `allocate_release` | Attributable content/metadata change with zero unresolved items; or executable implementation change reproduced by isolated cold rebuild; or public shared library implementation change with unchanged `DT_NEEDED`/symbols, `verified_compatible` type ABI, and reproduced cold rebuild. |
| 5 | `benign_nondeterminism` | Every finding is benign (e.g., BTF type order, `.pyc` source mtime, gzip header mtime, pure timestamp-only text diff). Never allocates a release. |
| 6 | `review_before_allocate` | Any unresolved item: `DT_NEEDED` order change (e.g. `librsvg`), missing/insufficient type ABI evidence, unverified executable implementation change, plugin/private-library contract, or high-cost recipe skipped from automatic cold rebuild. |

## 2. Diagnostic Checks (`scripts/diagnose-apk-rebuild.py`)

- **Trust & framing**: Verifies signatures via `--keys-dir` (or repo
  `public-key.pem` in standalone mode). Checks `ADBd` raw DEFLATE framing to
  EOF with zero trailing bytes before allowing `reuse_published`.
- **Complete APK schema**: Compares `info` (excluding derived `hashes` and
  `installed-size`), `scripts`, top-level `triggers`, `replaces-priority`,
  unrecognized top-level keys (flagged `unknown`), directory/file `acl`,
  `xattr`, `mtime`, symlink `target`, and file content hashes.
- **Content analysis**:
  - Text timestamp detection masks date/time substrings across the entire file
    and only marks `benign` when the entire normalized content is identical
    (config value changes on dated lines are `change`).
  - ZIP archives check duplicate member names (`unknown`) and Unix mode bits
    (`change`) in addition to member payloads.
  - Loadable ELFs are inspected with `pyelftools` for `e_machine`,
    `EI_CLASS`/`EI_DATA`/`EI_OSABI`, `PT_INTERP`, `PT_LOAD`/`PT_GNU_STACK`/
    `PT_GNU_RELRO`, ordered `DT_NEEDED` (preserving order and duplicates),
    `DT_SONAME`, `DT_RPATH`/`DT_RUNPATH`, `DT_FLAGS`/`DT_FLAGS_1` (`DF_1_PIE`),
    semantic `.gnu.version_r`/`.gnu.version_d`, and exported/imported dynamic
    symbols. Objects are classified into `executable`, `public_shared_lib`,
    `plugin`, `private_shared_lib`, or `relocatable`.

```sh
python3 scripts/diagnose-apk-rebuild.py base/librsvg-2.62.4-r5.apk
python3 scripts/diagnose-apk-rebuild.py --json --abi-store tmp/rebuild-evidence/abi OLD.apk NEW.apk
```

## 3. Atomic Ledger Allocation, Approvals & Recovery (`scripts/allocate-rebuild-releases.py`)

- **Deduplication**: Merges identical `(name, version, old_sha256, new_sha256)`
  copies projected into both a source repo and `custom/`; raises an error if
  the same identity has conflicting digests.
- **Digest-bound manual approval**: Items in `review_before_allocate` can be
  approved without broad `--accept-unknown` by passing `--approval FILE`:

```json
{
  "schema": 1,
  "policy_version": "phase2-evidence-v1",
  "report_sha256": "<report.report_sha256()>",
  "old_sha256": "<published apk sha256>",
  "new_sha256": "<candidate apk sha256>",
  "name": "resources",
  "reason": "Reviewed executable diff; load contract and imports unchanged"
}
```

- **Atomic writes & permanent reservations**: Re-checks `ledger_sha256` and the
  active published snapshot alias before writing, replaces
  `configs/apk-elf-rebuilds.mk` via same-directory temporary file + `fsync` +
  `os.replace`, and records superseded effective releases as
  `# reserved: ELF_REBUILD_<name>_<recipe> -> <old_ver>` so they are never
  reused.
- **Crash recovery**: Persists allocation records in
  `tmp/.apk-rebuild-allocations.json`. Retrying after an interrupted rebuild
  recovers the existing reservation instead of allocating a duplicate release.
- **Post-allocation payload verification**: After rebuilding the newly allocated
  release, `verify_rebuilt_package()` verifies its signature and compares it
  against the pre-bump candidate; only release-bump metadata differences are
  permitted, and any extra ELF/payload drift fails closed.

## 4. Out-of-APK Public Library Type ABI Evidence (`scripts/elf-type-abi.py`)

Public shared library type evidence is stored outside APKs (never inside APK
payloads) keyed by the **final stripped ELF SHA-256** (`<store>/<sha256>.abi.json`):

```sh
python3 scripts/elf-type-abi.py capture \
  --unstripped build_dir/.../libdemo.so.1 \
  --stripped staging_dir/.../libdemo.so.1 \
  --store tmp/rebuild-evidence/abi \
  --package libdemo --version 1.0-r1 --path usr/lib/libdemo.so.1

python3 scripts/elf-type-abi.py compare \
  --old OLD_STRIPPED.so --new NEW_STRIPPED.so --store tmp/rebuild-evidence/abi
```

- Verifies the unstripped ELF matches the final stripped ELF on architecture,
  SONAME, ordered `DT_NEEDED`, and exported dynamic symbols before recording.
- Uses `libabigail` (`abidw`/`abidiff`, decoding all 4 exit status bits:
  `ERROR=1`, `USAGE_ERROR=2`, `ABI_CHANGE=4`, `ABI_INCOMPATIBLE_CHANGE=8`) when
  installed, paired with native `pyelftools` DWARF extraction of exported
  function signatures and reachable `struct`/`union`/`enum` layouts.
- Requires `.debug_info` presence (not merely `.eh_frame`) and 100% exported
  symbol coverage; missing DWARF or incomplete coverage returns
  `insufficient_coverage` and falls back to `review_before_allocate`.

## 5. Build Input Provenance & Guarded Isolated Cold Rebuild (`scripts/rebuild-cold-verify.py`)

When `--cold-rebuild` is enabled on `scripts/build-and-publish.py` (never
triggered on hot builds with no same-version conflicts):

- **Input provenance**: Fingerprints recipe files, transitively included
  `include/*.mk`, relevant `.config` symbols, toolchain binaries, ledger hash,
  and a strict environment whitelist (`SOURCE_DATE_EPOCH`, `MAKEFLAGS`,
  `NINJA_ARGS`, `CARGO_BUILD_JOBS`, `LANG`, `LC_ALL`, `TZ`) — never secrets or
  signing keys.
- **Single isolated cold rebuild**: Runs at most once per conflicting source
  recipe in a private temporary `BUILD_DIR`/`BIN_DIR` with result caches
  disabled (`CARGO_INCREMENTAL=0`, `SCCACHE_DISABLE=1`, `CCACHE_DISABLE=1`,
  `RUSTC_WRAPPER=""`), without mutating the active checkout, staging, or kernel
  sequence.
- **Drift forensics**: If identical inputs produce different payload bytes,
  allocation stops with zero ledger writes and saves both APKs, `inputs.json`,
  `diagnosis.json`, and `run.json` under `tmp/rebuild-evidence/drift/`.
- **Default ban on high-cost recipes**: Recipes matching Qt/KDE, LLVM/Clang/Mesa,
  Rust/Cargo (by name or `include/{rust-*,gnome-rust,cargo}.mk`), browsers,
  QEMU, or core toolchains are **blocked from automatic cold rebuild by
  default**. Instead, the tool writes an evidence-backed manual review report
  under `tmp/rebuild-evidence/provenance/review-*.json` and stops in
  `review_before_allocate` (`high_cost_cold_rebuild_blocked`). Explicit
  authorization is required to cold-rebuild them:

```sh
python3 scripts/build-and-publish.py --allocate-rebuilds --cold-rebuild \
  --authorize-cold-recipe resources
# or for all high-cost recipes in one invocation:
python3 scripts/build-and-publish.py --allocate-rebuilds --cold-rebuild \
  --allow-high-cost-cold-rebuild
```

## 6. Publisher, Dry-Run & Preflight Integration

- **Outer-framing reuse (`scripts/publish-lan-apk-feeds.py`)**: During
  incremental non-frozen publication, when a verified candidate matches the
  published APK's uncompressed ADB stream, the publisher selects the published
  APK before `custom/` projection and indexing, recording both
  `candidate_sha256` and `selected_sha256` in `manifest.json` and the preflight
  receipt. Frozen artifact bundles never substitute files.
- **Preview safety (`scripts/build-and-publish.py`)**: Standalone publish
  `--dry-run --allocate-rebuilds` returns a `dry-run-conflict` plan with zero
  ledger writes and zero `make` invocations.
- **Receipt binding (`scripts/apk-upgrade-preflight.py`)**: Upgrade preflight
  receipts bind `diagnoser_sha256`, `allocator_sha256`, `elf_type_abi_sha256`,
  `cold_verify_sha256`, and `reused_published_apks`; `authorize()` rejects
  promotion if any policy or tool file changed after validation.
