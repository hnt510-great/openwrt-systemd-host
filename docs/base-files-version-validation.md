# base-files immutable version validation — 2026-11-21

## Scope

This records the fix for recurring `base-files` same-version publication failures.
The package embeds the checkout revision and build timestamp, while its former APK
identity used only the package-local `COMMITCOUNT` and upstream merge-base hash.
A local commit could therefore change signed content without changing its version.

The APK identity now adds the checkout-wide Git commit count and actual HEAD hash.
The rootfs version lock uses the effective package `VERSION`, including any legacy
ELF rebuild mapping. See [same-version APK rebuild diagnosis and release allocation](apk-rebuild-release.md).

No VM was run because this changes package identity and build metadata, not runtime
behavior. The focused host tests, an actual package build, a complete image build,
and the coordinated physical-router upgrade preflight cover the changed path. No
physical device was flashed, and publication did not install anything on the router.

## Artifacts

- Image: `bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz`
  - Size: 1,352,481,148 bytes
  - SHA-256: `579aa7924c8714418c207cc63f879bb64315a47b00cf51649a4bc8eefa1c52fa`
- APK: `target/base-files-1769.20.73443~5474fdb95c.apk`
  - SHA-256: `f8a667bded737f56390b8b3fb276ff630f2c741b38db5133bed1ff48613c84bb`
- Published userspace snapshot:
  `/srv/openwrt-feeds/public/snapshots/20261121T003238.701506Z`
- Kernel: `7.3.5-79-openwrt`; the existing kernel feed remained unchanged.

## Checks

| Check | Result |
| --- | --- |
| Reproduce the former failure | Failed as expected in the second run: revision/build-date changes under `1769.20~e7f788a9c1` |
| Historical allocator compatibility | Passed; 16 tests |
| Focused source-version tests | Passed; 4 tests, including two commits with identical timestamps |
| APK syntax and ordering | Passed for archive fallback, first/second Git commits, and old-to-new migration |
| DUMP and SDK lock behavior | Passed; deterministic DUMP placeholder and explicit `BASE_FILES_VERSION` override |
| `base-files` package build | Passed in 22 seconds; APK metadata and `base-files.version` both report `1769.20.73443~5474fdb95c` |
| `git diff --check` | Passed |
| Complete build and router upgrade preflight | Passed |
| Final publication without `--allocate-rebuilds` | Passed; no same-version rejection and no release allocation |
| Full `test-apk-source-versions.py` | The unchanged recipe-release guard reported 17 current-tree errors for existing feed/ledger reservations; the four focused tests passed independently |

## Final workflow timing

The final command was equivalent to `./scripts/build-and-publish.sh -j16`, with a
wrapper that only records timing and enables the existing publication progress
callbacks. No release-allocation option was used.

| Stage | Seconds |
| --- | ---: |
| `build.prepare-tmpinfo` | 1.557 |
| `kernel.reserve-generation` | 0.996 |
| `build.make` | 652.706 |
| Wait for publication lock | 0.001 |
| Read and stage APKs | 9.768 |
| Read router baseline and check trackers | 2.037 |
| Prepare userspace feeds | 29.664 |
| Prepare kernel feed | 1.308 |
| Record snapshot hashes | 1.791 |
| Simulate router upgrade | 5.563 |
| Upgrade preflight passed | 0.002 |
| Verify prepared userspace snapshot | 1.631 |
| Verify prepared kernel snapshot | 0.083 |
| Recheck router before promotion | 1.766 |
| Save publication receipt | 0.006 |
| Promote userspace feed | 1.638 |
| Promote kernel feed | 0.083 |
| Clean up staging snapshots | 0.053 |
| Publication complete marker | 0.000 |
| **Publication total** | **55.395** |
| **End-to-end total** | **711.590** |

## Evidence

Evidence is kept outside the repository at:

`/srv/openwrt-validation/base-files-version-validation-20261121-nE1YLL/`

It contains the rejected, automatically allocated, and fixed workflow logs, the
verbose package build log, focused and complete test output, and `SHA256SUMS`.
