# Publication readiness

A successful firmware build covers selected packages. Incremental feeds also
retain APKs for packages no longer selected in `.config`. Those retained APKs
still need current ELF metadata and compatible runtime dependencies.

The October 30 failures had three causes:

- Unselected `openwrt-needrestart` and `systemd-openwrt-services` APKs predated
  the ELF inventory migration and were never rebuilt by ordinary selected builds.
- Upstream `ca454c00b6` removed `kmod-iptables`. The hidden compatibility recipe
  now depends on `kmod-nf-ipt` and supplies generation metadata without duplicating
  its module or autoload files.
- A previous direct-APK deployment added checksum locks for five logical module
  trackers absent from the original world. Those locks prevented a new ABI from
  being selected. Their exact provenance was checked before restoring bare names;
  versioned generation payload protection pins were preserved.

## VM validation policy (updated 2026-11-14)

VM validation is not a blanket prerequisite for publication. When a change
introduces no major behavior change and no new functionality, do not require
or run a VM solely to publish it. Examples include documentation changes,
routine compatible package updates, release/ELF metadata corrections and
small fixes within an already validated behavior. Classify the actual diff
and dependency impact: a version bump alone does not prove a change is small.

Major behavior changes or new functionality need relevant runtime validation
before publication. Kernel changes require VM validation for a kernel series
upgrade (for example, 7.3 to 7.4) or broad kernel configuration changes. Routine
point releases, small patches and narrow configuration changes use the package,
module, ABI and coordinated publication checks. Use a disposable VM for relevant
boot/init, installer/storage, APK transaction/recovery and routing/firewall changes.
For hardware or desktop/client behavior a VM cannot cover,
record the appropriate device/client checks and any remaining gaps instead
of treating a generic boot/network VM pass as acceptance. Follow explicit
user-requested checks and applicable feature validation procedures.

For routine publication, run the relevant source checks and package builds,
then the coordinated publication preflight. Signature, ELF/ucode and dependency
checks, immutable package identities, retained-APK auditing, reachable-router
baseline checks and both upgrade simulations remain mandatory where applicable.
Skipping a VM does not bypass any of these gates.

Record the change scope, checks performed and why VM validation was unnecessary
(for example, “VM not run: routine compatible package update; no major behavior
change or new functionality”). Keep source/build results, VM results, feed
publication, physical installation, reboot and client acceptance separate.
Historical VM results describe their dated artifacts, not a newly built image.

The ordinary `build-and-publish.sh` and `publish-changed-feeds.sh` paths do not
invoke a VM. The disabled scheduled-maintenance workflow has its own implemented
exact-image VM gate; it is not the required route for routine publication.
This policy update does not change that runner or enable its schedule. See
[scheduled maintenance](scheduled-maintenance.md).

## Build and validate

For routine rolling publication from current sources:

```sh
./scripts/build-and-publish.sh --rolling -j16
```

Add `--dry-run` to build the same packages and run the coordinated preflight
without advancing the feed pointers. Use `build-only --rolling` for local APK
builds. The rolling build includes signed kernel packages and checks the
expected APK identities against the candidate feeds. Use the
[rolling build and VM artifact workflow](incremental-build-acceleration-validation.md)
for full media validation and saved candidates.

For a complete build followed by publication:

```sh
./scripts/build-and-publish.sh -j3 V=s
```

Complete builds refresh package metadata and include unselected retained APKs
whose current recipe version has an explicit ELF migration mapping. Both local
outputs and the existing ABI feed are considered. These selections are make
command-line overrides; they do not enable the packages in `.config`. Explicit
command-line package selections are respected. Already migrated or newer APKs
are not rebuilt by this rule, and it does not invent release bumps or overwrite
published identities.

To build without publishing, then validate the result:

```sh
python3 scripts/build-and-publish.py build-only -j3 V=s
./scripts/publish-changed-feeds.sh --dry-run
```

The publication wrapper validates existing outputs; it does not run a build or
edit router world constraints. Its early router check reports missing target
trackers and incompatible installed checksum/version locks before expensive feed
staging. That early check is the complete router baseline scan the simulation
reuses; both actual solver simulations and a second complete scan, which must
match it, remain mandatory before promotion. A baseline change at any point
after the early check requires a retry.

The ELF audit reports all missing, stale or malformed inventories in one pass,
including retained migration alternatives. An excluded package can be rebuilt
explicitly with `make package/<source>/compile CONFIG_PACKAGE_<name>=m V=s`.
Use the allocated migration release if one exists; otherwise allocate a new
release rather than rewriting an existing published APK.

Long solver errors retain their opening conflict and final blocker. Review
explicit world constraints individually: do not strip all locks, remove installed
module selections, relax ABI validation, or delete protected generation packages
to make a publication pass. When deploying exact APK files, preserve the original
logical selections and avoid leaving new checksum locks on logical trackers.

Publication still blocks genuinely incomplete builds, missing compatibility
ports, changed immutable APKs, invalid signatures, unreachable routers and
unsatisfied dependencies. A dry-run cannot guarantee a later run if the inputs
or router baseline change. Neither wrapper installs packages or reboots a router.

## Validation on 2026-10-30

The focused suites passed 136 tests: 59 coordinator, 28 upgrade preflight,
23 ELF ABI and 26 LAN publisher tests. They include signed APK fixtures,
multiple missing/malformed inventories in one report, unselected/local/retained
migration outputs, preservation of explicit selections and protected pins,
early rejection before feed staging, baseline changes and long solver errors.
Complete-build argument forwarding is tested with mocked make; no new full
firmware build is implied.

The real `publish-changed-feeds.sh --dry-run` completed successfully against the
router running g40. Tracker/lock readiness ran at 4.7 seconds and the full
preflight passed; active feed aliases and `.config` were unchanged. No feed
promotion, router package transaction or reboot was performed for this change.
Evidence is under `bin/validation/publication-prevention-20261030/`.
