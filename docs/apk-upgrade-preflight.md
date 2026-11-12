# APK upgrade preflight

The signed native-systemd publisher now validates an upgrade from the configured
router, rather than treating a self-consistent new build as proof that an
installed system can upgrade. Normal router commands remain:

```sh
sudo apk update
sudo apk upgrade --simulate --plan-json /root/apk-upgrade-plan.json
sudo apk upgrade
```

The new APK options require `apk-mbedtls`/`apk-openssl` 3.0.5-r13 or newer.
An ordinary full managed upgrade selects the newer rolling kernel when its ABI
changes, while honoring explicit world version and repository-tag constraints.
An unported installed module therefore blocks the full transaction instead of
quietly leaving the old kernel and upgrading other packages.

With [kernel packages](kernel-upgrade.md), a full upgrade installs the newest
`linux-image-<release>` next to the running kernel, and kmods are
kernel-independent configuration packages, so there is no per-module ABI
transition to validate. The router baseline records the state model.
`generations` routers (schema 1) are checked on the `--userspace-only`
migration step: their kernelctl cannot yet validate kernel packages, and the
receipt records `migration_step: userspace-only`. `packages` routers
(schema 2) get one full simulation against the kernel channel and the
`current` userspace snapshot. An unblessed or counted kernel never blocks
publication.

If a full upgrade is blocked, userspace can be selected explicitly:

```sh
sudo apk upgrade --userspace-only --simulate --plan-json /root/userspace-plan.json
sudo apk upgrade --userspace-only
```

This mode pins installed kernel packages, images, modules, native headers and
packages with actual kernel dependencies by identity in a private solver world.
It rejects transactions that would add, remove or reinstall ABI-bound packages.
It does not persist those extra constraints. It requires a full upgrade without
package arguments, `--available`, `--prune` or `--preupgrade-only`.

## Transaction checks

The patched APK shares its solver and kernel-policy checks between simulation,
normal commit, and the full preflight before an early APK/support-package
upgrade. The actual transaction uses the validated changeset under APK's
database lock. Existing kernel trial, protected-generation and recovery rules
remain enforced by `kernelctl`.

From apk 3.0.5-r18 a started commit defers termination signals until its
database is written. A journal under `/lib/apk/db/transaction/` lets
`apk-resume` finish a commit cut off by power loss, a crash or SIGKILL. While
that journal is pending, other commits and publication (router baseline) are
refused. See [interrupted APK transactions](apk-transaction-recovery.md).

Before a managed transaction writes a package, APK downloads remote payloads
into its cache and verifies all new payloads against their index identities and
signatures, including local repository files and existing cache entries. A
managed remote transaction requires an active cache; `--cache-dir` can select
another suitable location. Simulation does not download payloads or change the
installed database, world or kernel state.

`--plan-json FILE` writes a private mode-0600 schema-1 report. The path is in the
caller's filesystem, even with `--root`. The fields are:

- `mode`, `status`, `blockers`: preflight mode, result and stable blocking codes.
- `inputs`: SHA-256 of world and installed metadata.
- `indexes`: printable repository URLs and SHA-256 of locally available index
  bytes; an unavailable index hash is `null`.
- `kernel`: before/after ABI and immutable image identities.
- `changes`: names, before/after versions, origins, APK metadata identity digests
  and reinstall flags. `package_digest` is an APK identity, not a whole-file hash.

A passed plan is not an installation receipt. Check the command exit status
for download, script, transaction and post-policy failures. A multi-stage APK
self-upgrade replans after re-execution. Kernel upgrades only request a reboot;
they do not reboot automatically.

## Publication gate

Use `scripts/publish-changed-feeds.sh`, including `--dry-run` for a complete
publication preflight. The canonical production destination in
`configs/lan-apk-feeds.json` requires `upgrade_preflight.ssh_target`; it currently
identifies `builder@192.0.2.1`. Direct low-level production publication is
rejected. Low-level dry runs only validate their individual repository view.

The coordinator holds a destination-wide publication lock and prepares signed
userspace and kernel snapshots before changing either active pointer. It then:

1. Reads a consistent router baseline under APK's database lock, including
   package metadata, world, running ABI, protected constraints, kernel state,
   public-key/configuration hashes, APK identity, boot ID and the ELF
   fingerprint of installed files. Pending trials or unreachable routers stop
   publication. This complete scan happens once, before feed staging; the
   simulation and receipt are bound to it.
2. Checks installed logical kmods against the candidate ABI's actual trackers
   and generation payloads. This check does not depend on the new `.config`.
3. Fetches the candidate signed indexes into temporary router directories,
   checks their hashes and simulates the real router transaction. Its current
   ABI feeds remain in effect; staged userspace indexes join the simulation
   when they match the running ABI. For an ABI transition, a second simulation
   replaces managed feeds only in a temporary repository list with the staged
   target-ABI views, preserving external feeds. Both upgrade paths must pass,
   alongside the publisher's signature, dependency-ABI and ucode checks.
4. Rechecks the router baseline, policy/rule hashes and every prepared file.
   Snapshot hashes are recorded before simulation; the coordinator rechecks
   both views before either pointer moves. The preflight helper does not
   repeat this full-file check immediately before the coordinator does it.
   The router is scanned completely a second time only after both snapshots
   are rehashed, immediately before promotion, and must match the step 1
   baseline; any change since step 1, including during simulation, requires
   a retry. A publication therefore performs two complete router scans plus
   the simulations. Standalone `preflight()` callers keep their own
   post-simulation rescan unless they pass `recheck=False` and perform this
   promotion check themselves.
   Each promotion also rechecks its own view at the commit boundary.
   A production dry run discards its own prepared snapshots. Formal publication
   writes a private receipt, exposes userspace first, then the kernel channel.
   If committing the kernel pointer fails, the coordinator restores its own
   userspace pointer. Post-commit snapshot-GC failures are reported separately.

Production receipts live in `<destination>/upgrade-receipts/` and bind the
baseline and prepared snapshot hashes. They omit raw world/database contents.
The exact prepared files are promoted; publication never rebuilds a second
candidate from mutable `bin/`. Scheduled maintenance retains its exact-image
boot/network VM gate and also uses this same upgrade gate. Neither process
installs packages on the physical router.

## Explicit empty-package migrations

`configs/apk-migrations.json` is the central schema-1 registry. Each rule has
`from`, a nonempty `to` list, `type: empty-compat`, and an audit `reason`. The
initial rule maps `kmod-nf-log6` to `kmod-nf-log` after upstream removed the empty
IPv6 logging package.

The registry currently supports kernel packages. A shared Make template emits
normal hidden `KernelPackage` definitions and their symbolic
`default y if OPENWRT_KERNEL_UPGRADE`. Normal APK splitting creates both the
logical tracker and ABI-pinned generation payload. An existing upstream recipe
with that name, malformed rule, duplicate, cycle or missing replacement fails.
The registry and generator invalidate both package scanning and kernel-input
fingerprints; changing them requires the normal new-generation build workflow.
For an existing configuration that has not yet acquired a new hidden selection,
the template builds the compatibility APK for the channel without modifying
`.config` or forcing it into that image.

During publication, an empty migration may own only its package bookkeeping
list and generation metadata. Any real file in the installed tracker or its
payload blocks automatic migration. Changes involving modules, services or
configuration paths require a dedicated port/recipe and validation. Unknown
installed-module removal blocks publication until a real migration is supplied.

## Bootstrap and acceptance boundaries

An old APK r11 process can append existing protected constraints to world while
installing the first new APK. Before that separately authorized deployment,
capture world and protected state and simulate the exact signed transaction.
Compare the resulting world to the capture: restore only newly added entries
that exactly match protected constraints, retaining every original constraint.
Subsequent r13 transactions keep their extra pins solver-local. This bootstrap
behavior was reproduced and checked in a disposable VM. The subsequent
authorized physical deployment is recorded in `kernel-upgrade-validation.md`;
its original world was preserved exactly.

Source/unit checks, VM package/transaction/reboot checks and physical-router
read-only simulations are separate evidence. A solver simulation does not prove
device boot, driver functionality, package scripts or a full userspace rollback.
Publication and physical installation remain separate authorized operations.
