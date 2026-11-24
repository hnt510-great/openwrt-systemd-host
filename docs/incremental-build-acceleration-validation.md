# Rolling builds and VM artifacts

Use the new rolling entry point for routine upgrades on the configured native
systemd x86/64 target.

```sh
./scripts/build-and-publish.sh --rolling -j16
./scripts/build-and-publish.sh --rolling --dry-run -j16
python3 scripts/build-and-publish.py build-only --rolling -j16
```

The rolling target builds the package dependency graph and assembles the
kernel channel from the same compiled kernel and modules as a full build.
It skips rootfs installation, firmware image creation, and the installer ISO.
The coordinated publisher generates and signs the feed indexes. The
`--dry-run` command still builds locally and may reserve a kernel generation.
The original commands without `--rolling` keep their full build behavior.

The rolling build collects the APK paths, versions and architectures evaluated
by Make, including ABI suffixes and ledger mappings. The prepared feed must
contain this package set with the same staged contents. A missing build output,
a conflicting identity or a higher version retained for a selected package
blocks reuse or promotion of the snapshot. Historical compatibility APKs stay
available. Current sources mean this checkout and its synced feeds, with the
working configuration and ledger. The build does not fetch upstream versions.

When explicitly enabled, automatic release allocation reruns the rolling
package graph after applying the ledger, so exact reverse dependencies can
be repacked. An allocation from an unsuccessful retry stays in the ledger for
inspection. Preview and allocation are separate operations.

## VM validation

Kernel changes require VM validation for a kernel series upgrade or broad
kernel configuration changes. Routine kernel point releases, ordinary patches
and narrow config changes use the package, module, ABI and publication checks.
Use the combined EFI image for relevant boot and runtime behavior and the
installer ISO for actual installation and offline component checks. For a
rolling upgrade regression, upgrade a VM from the previous release against an
isolated feed containing the candidate APKs.

```sh
python3 scripts/build-and-publish.py build-only --vm-artifacts /path/to/new/candidate -j16
./scripts/publish-changed-feeds.sh --artifacts /path/to/new/candidate --dry-run
```

Use the frozen `image.img.gz` and `installer.iso` for the VM checks. Record
their SHA-256 and that of `manifest.json` with the VM results. On authorization,
rerun the frozen APK publication without `--dry-run`. It verifies the complete
bundle, rechecks the captured package inventory and prepares the original APKs
for current router preflight. The disabled
scheduled workflow keeps its existing build and VM gate.

## Measuring the change

Settle each build path once and measure at least three warm builds with unchanged
inputs. Repeat the comparison with the same single package release change in
each paired run. Use fresh `BUILD_TIME_LOG` files and separate wall timing for
the build and isolated publisher. Record cleanup, package compilation and
packing, kernel bundle, rootfs, image, ISO and publication times. For a matched
comparison, hold the source, config, signing key, timestamp, retained directories
and initial feed state fixed.

Compare APK identities, dependency metadata and byte hashes across paths, then
check that rolling followed by a full build produces valid fresh media.
Historical full-build stage totals include kernel bundle and other shared work
and cannot be counted as rolling savings.

The original investigation recorded per-stage timings, warm-build invalidation
evidence, and profiling follow-ups. Read that historical handoff from the
repository root when investigating the remaining performance gap:

```sh
git show 687fab97f03e0bbafa3724e2563542b9b8434aef:docs/incremental-build-acceleration-plan.md
```

## Host checks

The signed fixture suites cover missing current outputs with retained older
APKs, equal source snapshots with altered retained bytes, retained higher
versions, reuse of the same rolling graph and timestamp after allocations,
and stale media rejection before artifact capture. The existing publisher,
kernel bundle, release allocation, router preflight and scheduled-maintenance
suites exercise the shared paths.

On 2026-11-21, the real rolling retry built kernel generation 81 in 150.09s.
A subsequent full media build completed in 333.66s. The 1,561 APKs present
after the rolling build matched byte for byte after the full media build and
after the later timing runs. The ISO static checks passed, and an isolated
frozen-artifact publication dry-run passed with 1,398 expected userspace APKs.
The isolated destination had no router preflight policy.

Three subsequent rolling/full pairs took 81.39/232.70s, 182.87/224.63s,
and 182.73/223.06s respectively. These are elapsed build-only timings, not a
validated no-op comparison: the runs executed package packing and later rolling
runs also relinked the kernel. Their median times were 182.73s and 224.63s.
The cause of this incremental invalidation remains to be investigated.

The initial parallel rolling build reported a kernel package failure. A serial
kernel package rebuild and the rolling retry succeeded. A later first warm
attempt reported a parallel luci-lib-ip failure; its serial rebuild succeeded.
Neither quiet log captured the underlying error. Source-version tests report
15 existing recipe/ledger reservation errors in the current tree. The current
check did not publish feeds, install router packages, or run VM boot tests.
Logs, timing events, checksum lists and the ISO static receipt are retained in
`/srv/openwrt-validation/rolling-build-validation-20261121/`.
