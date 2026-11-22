# Same-Version APK Rebuild Diagnosis & Release Allocation Validation

- **Date**: 2026-11-22
- **Implementation commit**: `1221771bb2ac65a71de079ac951d2b9481edc388`
- **Guide**: [apk-rebuild-release.md](apk-rebuild-release.md)
- **Handoff & phased plan**: [apk-rebuild-release-handoff.md](apk-rebuild-release-handoff.md)

## Real Replay Samples Verified

| Sample | APK Path | SHA-256 |
|---|---|---|
| Published `librsvg` | `/srv/openwrt-feeds/public/snapshots/20261122T052658.620916Z/base/librsvg-2.62.4-r5.apk` | `1314716a2564ca33058393d00064615b5cbf069443f9a417c4b72e8299d40968` |
| Local `librsvg` | `bin/systemd/packages/x86_64/base/librsvg-2.62.4-r6.apk` | `7db64267a001dac6672241d847f2b0dfb3ce799f1bc11dda15fc17be11994c49` |
| Published `resources` | `/srv/openwrt-feeds/public/snapshots/20261122T052658.620916Z/base/resources-1.10.2-r2.apk` | `97a950a6bc3286ce62b7dfb6097f9b5228c25a8f7baf97a36491880a20c2b20c` |
| Local `resources` | `bin/systemd/packages/x86_64/base/resources-1.10.2-r3.apk` | `c545395178872702f16584bf4e1df79e85af2f563ba637557545d3f7520a88d5` |

## Host, Real-Compiler & Signed-Feed Checks

All commands were executed from `/srv/openwrt` with
`PYTHONDONTWRITEBYTECODE=1`.

| Check | Result |
|---|---|
| `python3 scripts/tests/test-diagnose-apk-rebuild.py` (mixed findings, dated config lines, top-level ADB schema, ZIP modes/duplicates, outer DEFLATE reuse + negative cases, real `librsvg` & `resources` replays) | PASS (21/21) |
| `python3 scripts/tests/test-allocate-rebuild-releases.py` (`unknown + so_changed` refusal, `base`/`custom` dedup & digest conflict, digest-bound approval & policy mismatch, atomic writes, `# reserved:` retention, concurrency check, crash recovery, dry-run zero side effects, post-allocation payload verification) | PASS (22/22) |
| `python3 scripts/tests/test-apk-rebuild-phase2.py` (real `gcc -g -shared -fPIC` + `strip --strip-all` type ABI compatible/param-change/struct-layout-change/no-DWARF cases, `abidiff` exit bitmask, secret-free input provenance, single-shot isolated cold rebuild stable & drift forensics, hot-build zero cold rebuilds, Qt/LLVM/Rust high-cost default block & explicit authorization) | PASS (10/10) |
| `python3 scripts/tests/test-lan-apk-publisher.py` (includes signed-feed outer DEFLATE reuse recording `candidate_sha256` and `selected_sha256`) | PASS (27/27) |
| `python3 scripts/tests/test-elf-abi.py` | PASS (23/23) |
| `python3 scripts/tests/test-ucode-abi.py` | PASS (6/6) |
| `python3 scripts/tests/test-build-and-publish.py` | PASS (73/73) |
| `python3 scripts/tests/test-apk-upgrade-preflight.py` | PASS (37/37) |
| Section 2 behavioral probes (mixed report, `unknown + so_changed`, `triggers`, dated config line) | PASS (4/4) |
| `git diff --check` | PASS |

**Total host & temporary signed-feed assertions**: **219/219** passed.

## Real-Case Replay Observations

- **`librsvg-2.62.4-r5.apk` vs `r6.apk`**: Verified under repository public
  key; classified `usr/lib/librsvg-2.so.2.62.4` as `public_shared_lib`,
  detected `DT_NEEDED` reordering at positions 6–9 (`libc.so.6`,
  `ld-linux-x86-64.so.2`, `libgcc_s.so.1`, `libm.so.6` -> `libm.so.6`,
  `libc.so.6`, `ld-linux-x86-64.so.2`, `libgcc_s.so.1`), confirmed semantic
  `.gnu.version_r` equivalence and 55 identical exported dynamic symbols,
  reported `missing_type_abi_evidence`, and stopped at `review_before_allocate`.
- **`resources-1.10.2-r2.apk` vs `r3.apk`**: Verified under repository public
  key; classified `usr/bin/resources` and
  `usr/libexec/resources/resources-processes` as `executable` (0 exported
  dynamic symbols, identical `DT_NEEDED` and load contracts), and stopped at
  `review_before_allocate` by default (also classified as a high-cost Rust
  recipe blocked from automatic cold rebuild unless explicitly authorized).

## Validation Scope

- **Covered**: Host unit tests, real `gcc`/`strip`/signed-APK compiler
  fixtures, real published/local APK replays, and disposable temporary signed
  feed publication tests.
- **Not executed**: Production LAN feed publication (`/srv/openwrt-feeds`),
  disposable VM boot tests, and physical router upgrades were not run because
  these changes are confined to host-side publication/diagnosis tooling and
  require separate authorization for production feed publication.
