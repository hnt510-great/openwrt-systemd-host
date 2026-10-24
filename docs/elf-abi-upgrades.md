# Shared-library ABI upgrades

APK packages built by this tree now declare their actual ELF library contracts.
For example, Sunshine linked against Boost 1.92 needs
`so:libboost_log.so.1.92.0`; boost-log provides that exact capability. APK cannot
replace that library with an incompatible SONAME while retaining its consumer.
The original recipe dependencies remain responsible for selecting build inputs,
non-ELF resources and dynamically discovered plugins.

## Build and publication

`scripts/elf-abi.py` reads ELF program headers and dynamic strings directly. It
does not run binaries or depend on the target loader. It handles 32/64-bit ELF,
endianness, stripped binaries, the ELF interpreter, SONAME, NEEDED, RPATH,
RUNPATH, root-relative symlinks and `$ORIGIN`. Relocatable objects/kernel modules
and static binaries do not create shared-library dependencies.

Public libraries provide `so:<SONAME>=0`; their ABI version is part of the
SONAME, rather than the capability's numeric version. Private libraries satisfy
only objects with a matching loader search path, and never become global
providers. A cross-package private library requires the owner's exact package
version. Inherited RPATH is distinguished from direct-only RUNPATH. The explicit
Firefox bootstrap and Samba module loader directories are documented in
`configs/elf-abi-policy.json`. Relative/unknown loader paths never count as ABI
proof: the remaining search paths must resolve the dependency.

Each native payload includes `/usr/lib/apk/packages/<name>.elf.json`. Staged
inventories identify the owners of private libraries. Each provider's
`pkginfo/<name>.sonames` file changes only when its public library capabilities
change; the existing library dependency stamps then rebuild affected consumers.

The publisher independently extracts and scans every newest candidate, including
retained incremental packages. Missing/stale inventories, absent dependencies,
inaccurate providers and unresolved libraries stop publication. Historical APKs
are retained for rollback but cannot satisfy this newest-candidate check. All
published package identities are immutable: changed bytes require a new version,
including metadata-only changes. The existing ucode interpreter/module ABI lock
remains active, since SONAME alone cannot describe that plugin ABI.

The coordinated release preflight also inventories actual installed ELF files.
It combines unchanged installed packages with the exact APK transaction plan
and validates the resulting file view. This catches old installed consumers
without `so:` metadata, rather than trusting a self-consistent new repository.
Receipts bind the scanner, loader policy, migration ledger, router state and
prepared signed snapshots. The complete transaction is simulated with
`--no-preupgrade`, avoiding the early self-upgrade solver's simulated state.

## One-time metadata migration

`configs/apk-elf-rebuilds.mk` records exact input package versions and their new
releases. It changes effective APK versions and matching exact dependencies,
without modifying upstream versions or hundreds of independent feed recipes.
Entries cease to apply when the source version changes. A normal subsequent
rebuild remains subject to immutable-publication checks; this ledger is not an
automatic permission to overwrite the same release.
For example, an original Sunshine r2 mapped to r3 must use r4 (or a newer
upstream version) for its next changed publication; merely setting the recipe
to r3 would still reuse an already published effective version.

Compatible signed payloads can be repackaged by `scripts/migrate-elf-abi.py`
inside fakeroot. Its audited plan records original package metadata, ELF
inventories, target versions, repository, workspace and output. The worker checks
all existing path contents, permissions, ownership, timestamps, symlink targets,
scripts and triggers after creating the new APK. Only the package file list and
the new inventory are added/updated. Incompatible consumers must first be built
from source; Sunshine is rebuilt against Boost 1.92 rather than repackaged.

An exact `libc=<old release>` world pin, or an APK checksum pin from a previous
offline installation, intentionally prevents an ordinary upgrade. Migration
maps only pins whose installed version exactly matches the audited ledger:
version pins stay version pins, checksum pins stay checksum pins, repository tags
are retained, and bare names stay bare. Kernel/generation pins are excluded.
The production preflight simulates this mapped world in a private mount
namespace without modifying the live world. The release receipt records the
precise changes. Unrelated constraints are never relaxed.

When a router intentionally pins an older upstream version, publish a metadata
rebuild of that version alongside the current candidate. The publisher audits
these explicitly registered alternatives and their library contracts. The final
router gate still checks a real single-version-per-package solver selection;
the pool of historical alternatives is not treated as an installable union.
This preserves, for example, a pinned Podman 5.x instead of turning a metadata
migration into an unsolicited major upgrade. Historical BIND/SQLite pairs are
handled together, including their exact library dependencies.

Deployment verifies signatures and hashes in an offline repository, configuration
and kernel state, then simulates the exact selected package identities. The
verified mapped world is installed immediately before the offline upgrade;
`--no-preupgrade` commits the audited full transaction. This avoids adding every
dependency to world, and preserves the repository's APK identity for checksum
pins (a legacy embedded package UID can differ from a v3 index identity).

`scripts/apply-elf-migration.py` implements the target operation. It backs up all
affected old/new paths, `/etc`, the package database and bookkeeping, preserving
ACLs/xattrs, and arms a 20-minute systemd rollback timer before writing world.
Rollback restores via unlink-before-extract so it does not truncate executable
inodes still mapped by running processes. The file/database backup also covers
packages whose exact old APK archive was not retained. A failed install rolls
back; successful installation leaves the timer armed until runtime acceptance.
Never use `--no-scripts`, `--allow-untrusted` or forced dependency removal.

## Validation

```sh
python3 scripts/tests/test-elf-abi.py
python3 scripts/tests/test-ucode-abi.py
python3 scripts/tests/test-apk-upgrade-preflight.py
python3 scripts/tests/test-lan-apk-publisher.py
python3 scripts/tests/test-build-and-publish.py
git diff --check
```

The tests use real ELF files and signed APKs. They cover SONAME upgrade rejection,
matched upgrades, private libraries, inherited loader paths, retained legacy
consumers, stable Make dependency stamps, inventory validation and preservation
of world-pin types. Record package builds, disposable-VM migration and physical
router validation separately.

SONAME checks detect library removal/name changes, not arbitrary incompatible
symbol changes hidden behind an unchanged SONAME or every `dlopen()` contract.

## Deployment record: 2026-10-24

Source validation passed 148 focused tests: ELF 15, ucode 6, upgrade preflight
20, publisher 21, coordinator 47 and package registry 39. Both repository
diff checks passed. Sunshine was rebuilt against Boost 1.92; D-Bus was rebuilt
as 1.16.2-r9. The dependency formatter preserves comma separators when mapping
exact releases, with a Make-level regression test. The publisher distinguishes
the userspace package `kmod` from kernel packages using the actual package name,
with a signed-package regression test.

An isolated QEMU guest completed a 799-package migration. A signed-package
fixture exercised the target helper's offline installation, checksum-pinned
world mapping, rollback timer and restoration of files, package database,
world and protected kernel state. The native D-Bus init guard also passed a
guest reload check without changing the native daemon PID or registering a
procd daemon. The disposable VM was stopped after validation.

The physical router accepted 802 distinct package changes, including the
supplemental userspace `kmod` migration. The final signed userspace snapshot is
`20261024T154855.366183Z`; its coordinated preflight selected the D-Bus r9
packages explicitly. Earlier compatible pinned Podman/BIND/SQLite versions
were preserved. Final actual-file checks covered all 1771 installed packages
and 1895 ELF files. All 801 ordinary native packages have the required ELF
dependency/provider metadata; immutable kernel packages remain on their
existing generation policy.

The router's boot ID, running g30 kernel, ABI and protected generation state
did not change. Forty service/application configuration hashes were preserved.
Sunshine is active with no restart loop, KMS/i915 capture and `h264_vaapi`;
its LAN HTTPS endpoint returns the expected unauthenticated 401, and Avahi
registration succeeds. All four existing containers retained their uptime.
System and both user managers report no failed units. Moonlight client video,
audio and input acceptance still requires an actual client connection.

A duplicate procd D-Bus instance had replaced the native bus socket. It was
removed and the native bus restored; logind/polkit were reconnected, and the
two user managers were reexecuted while retaining their workloads. Temporary
scope creation then passed for both users. The D-Bus init script now delegates
legacy start/reload calls to the native service and cannot start a second bus
when native systemd owns it. Its signed r9 package passed offline simulation
and installation while preserving the native bus PID.

The original `ABI unchanged` message is informational: it means the existing
kernel generation is retained. The cache error was a separate managed-upgrade
guard requiring authenticated payloads to be cached before writing packages.
The router now has `/etc/apk/cache -> /var/cache/apk`. On other installations,
an explicit cache works without this configuration:

```sh
sudo apk --cache-dir /var/cache/apk upgrade --simulate
sudo apk --cache-dir /var/cache/apk upgrade
```

The target migration is marked `accepted` and its rollback timer is inactive.
The private backup and signed offline bundle remain in
`/root/elf-abi-migration-20261024.kemUd7`; the temporary upload was removed.
No router reboot, firmware flash, commit or Git push was performed. The
existing `.config` hash remains
`f604073ef3439fb803927a18152f8c8215736e86ec06347ce9706ba4d3229877`.

The journal also recorded a NetBIOS WORKGROUP master-browser response from
another LAN host. This does not indicate an ELF dependency failure; no LAN
election configuration was changed. Existing long-running processes can still
appear in needrestart after library updates; container network helpers and
unrelated workloads were retained for a later maintenance restart.
Those still require the recipe's explicit ABI policy and application tests.
