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

## Build and validate

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
staging. A fresh baseline and both actual solver simulations remain mandatory
before promotion. A baseline change during preparation requires a retry.

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
