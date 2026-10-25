# Protected kernel upgrades on x86 native-systemd OpenWrt

This APK/GRUB mechanism installs parallel kernel generations while retaining
OpenWrt's exact kernel ABI dependencies. It supports the existing x86_64 glibc,
squashfs, native-systemd image and its separate persistent extroot. It does not
flash disks, replace the original `/boot/vmlinuz`, reinstall GRUB's core, or
reboot. It keeps at most two versioned kernels in `/boot` and never removes the
legacy rescue kernel.

## Build and publish

The normal combined command now builds and publishes both feed types:

```sh
./scripts/build-and-publish.sh -j16
```

With the feature enabled, a full/default (`world`) build refreshes package
metadata and fingerprints the kernel's relevant inputs: target/kernel config
and patches, package-to-kernel configuration requests, selected module/header
sources (including feed symlinks and build dependencies), shared build/package
rules, compiler/tool identities and relevant build flags. Unrelated userspace
package source, version and selection changes do not advance the sequence.
Kernel/module source changes still advance it even when the OpenWrt ABI hash
does not change.

The local record is `tmp/.kernel-publication-inputs.json`. Identical inputs reuse
the recorded sequence and kernel build timestamp, including after a failed build
or publication. Pinning the timestamp prevents a userspace-only commit's new
`SOURCE_DATE_EPOCH` from changing the kernel bytes. A new generation initially
uses the explicit build timestamp, `SOURCE_DATE_EPOCH`, or current UTC time.
This timestamp applies only to kernel builds; firmware/userspace timestamps keep
their normal behavior.

The combined wrapper runs make with umask `022` so package directory/file ACLs
do not vary with the invoking shell's umask. A support package rebuilt with
different metadata still needs a new `PKG_RELEASE`: the publisher never replaces
the signed bytes of an already published filename. After bumping and rebuilding
only those support packages, use the publish-only commands below to retry a
completed kernel build without reserving another generation.

Missing input history, changed relevant inputs, an explicitly increased sequence
or a newer channel published elsewhere reserve an unused sequence above the
published channel. Unknown existing immutable image outputs are skipped.
Removing the local record therefore causes one conservative new generation.
Only `CONFIG_OPENWRT_KERNEL_SEQUENCE` in `.config` is updated when necessary;
other options and the saved profile are preserved. Failed builds never publish.
Source/config changes during a build are refused before publication. Existing
signed-byte immutability checks remain the final guard against unrecorded changes
or direct edits to generated build files.

Before reusing a recorded generation with an existing image APK, the wrapper
also compares the APK's kernel/config file hashes with the current compiled
`bzImage` and kernel `.config`, and checks the image's embedded build timestamp
against the local record. A changed timestamp or an out-of-band rebuild
can change the binary even when source fingerprints still match. Missing or
different compiled files reserve an unused generation while preserving the
existing APK. Use the wrapper for full builds so the reserved timestamp is
passed to make; plain package make targets do not reserve generations.

After make succeeds, the wrapper selects only the compiled generation and its
matching logical trackers, payloads and configured modules/headers. Stale kernel
artifacts in `bin/` are ignored without deleting them. Missing modules, wrong
signatures, dependency mismatches, stale sequences and changed published bytes
block publication. Both views are preflighted before either is exposed. The
ABI-specific userspace view is published first, then the kernel channel is
atomically switched. Existing ABI-local kernel packages and all published kernel
generations remain unchanged. New kernel trackers/payloads are supplied only by
the independent channel, avoiding a new tracker becoming visible too early.

For an already completed matching build, publish or preview without rebuilding:

```sh
./scripts/publish-changed-feeds.sh --dry-run
./scripts/publish-changed-feeds.sh
```

These commands do not advance the sequence. Package-only make targets keep the
current sequence and require a complete matching generation to exist already.
With an input record present, changed kernel inputs refuse a package-only build;
use a full build to reserve the matching new generation. A changed support package must
also bump its release rather than replace previously published bytes. With the
feature disabled, the wrappers retain the original ABI-specific-only behavior.
Neither wrapper contacts, installs packages on, or reboots a router.

The feature defaults to enabled when its native-systemd/squashfs dependencies
are satisfied. Both the working configuration and the maintained desktop profile
enable it explicitly. The saved profile's sequence 4 is a seed following the
initial validation generation 3; the combined wrapper chooses an unused sequence
for the actual channel automatically. A new independent publication history
starts at 1. The following illustrates configuration, not a sequence to reset an
existing build to. Normalize manual configuration changes with `make defconfig`:

```
CONFIG_OPENWRT_KERNEL_UPGRADE=y
CONFIG_OPENWRT_KERNEL_SEQUENCE=4
```

Increment the sequence for **every published change** to a kernel, its config,
module payload, or prepared headers. Reusing a sequence for changed bytes is
rejected. The combined full-build wrapper does this automatically when relevant inputs change; direct
`make`/low-level publisher use still requires managing the sequence explicitly.
The actual `uname -r` contains the Linux version, full OpenWrt config
hash, kernel release and sequence. External modules rebuild on sequence changes.
Build the kernel, packages and final image through the normal build pipeline.
Keep the original signing key and publish a complete matching set of all selected
modules, including out-of-tree modules and native headers.

The publication sequence orders candidates. On an adopted installation with an
installed image tracker, APK r11 keeps the installed kernel generation when the
exact OpenWrt ABI is unchanged and only `-gN` increases. It retains the image,
logical kmods and native headers together while allowing userspace upgrades.
The additional solver constraints are temporary and are not saved in world.
A real ABI change still upgrades the complete generation, even when the new ABI
hash sorts below the old hash. APK may describe that ABI tracker transition as a
downgrade; the immutable image and kmod generation still advance together.
Build and runtime validation is recorded in
[the validation report](kernel-upgrade-validation.md).

Publication and APK transaction preflights, explicit userspace-only upgrades,
and centrally registered empty-package migrations are described in
[APK upgrade preflight](apk-upgrade-preflight.md).

Kernel generation builds also select the hidden `kmod-nf-log6` compatibility
package by default. Upstream removed this empty package because `kmod-nf-log`
already supplies IPv4 and IPv6 logging through `nf_log_syslog`. Existing images
can still select `kmod-nf-log6` in APK world. Without a matching tracker and
generation payload, that old package pins the previous ABI and blocks upgrades;
the kernel policy also rejects dropping a selected module. The compatibility
package depends on `kmod-nf-log` and supplies the generation metadata without
adding a module or requesting obsolete kernel configuration symbols. Include
both its tracker and generation payload in the signed kernel channel. Removing
the world entry, pruning repositories, or forcing APK does not replace this
migration path.

```
python3 scripts/publish-kernel-upgrade-feed.py \
  --source bin/systemd --destination /path/to/test-feed --dry-run
python3 scripts/publish-kernel-upgrade-feed.py \
  --source bin/systemd --destination /path/to/test-feed
```

The publisher verifies signatures and image/module identity, keeps only the two
newest publication sequences with their matching images, modules, headers and
trackers, and atomically replaces `public/kernel-upgrades` with a signed snapshot.
Support packages keep at most two versions using APK version ordering. After a
successful switch, obsolete kernel-channel snapshots are deleted; dry runs and
failed validation leave the active channel intact. ABI-specific userspace feeds
and installed router rescue generations are unaffected. Serve
that directory through the existing feed server. It is a separate channel from
ABI-specific userspace feeds. `lan-apk-feeds` follows the **running** kernel's ABI
for userspace repositories and includes the kernel-upgrades channel after adoption.
Publishing here is a filesystem operation, not deployment to a router.
The combined publisher constructs an ABI-specific userspace view and a separate
kernel input. It retains existing ABI-local kernel files rather than replacing
their legacy same-ABI package bytes. For low-level manual publication, use a
source containing only the intended generation and matching trackers, and make
the corresponding ABI-specific userspace view available before the kernel
channel. This ensures feed selection after reboot has a valid destination.

## Adopt an existing installation

First install the signed support packages: patched `apk-mbedtls` (or the selected
APK backend), `ubox`, `systemd-openwrt`, `grub2`, `grub2-efi`, `grub2-editenv`,
`lan-apk-feeds` and `openwrt-kernel-upgrade`. Simulate that transaction first.
These support packages do not install a new kernel. Never force incompatible
modules or change ABI metadata to satisfy dependencies.

The system must have a healthy native systemd boot, working LAN/firewall/SSH,
a writable verified `/boot` bind mount, enough free boot space, and a persistent
overlay. Load the running kernel config, then adopt:

```
modprobe configs
kernelctl migrate
kernelctl check
```

Migration snapshots legacy modules, autoload rules and firmware, preserves the
original kernel and GRUB configuration, and adds direct rescue/systemd, procd and
failsafe menu entries. It unpins only the image builder's exact `kernel=` entry in
`/etc/apk/world`, retains the other constraints, and enrolls `linux-image-openwrt`.
Ensure the signed channel is configured before the next APK transaction.

On a freshly built opt-in image, the boot service performs adoption automatically
after the router services are healthy. Adoption must complete before a live APK
transaction can install a versioned image. Offline image assembly is permitted.

## Upgrade and trial boot

```
apk update
apk upgrade --simulate
apk upgrade
kernelctl check
grub-editenv /boot/grub/grubenv list
```

The ordinary upgrade resolves the rolling image tracker and all selected logical
kmods into immutable generation payloads when the ABI changes. A same-ABI `gN`
increase prints `Keeping installed kernel generation: ABI unchanged.` and keeps
the installed kernel/module/header trackers, including for targeted tracker or
kmod upgrades. This does not arm a new kernel trial or require a kernel reboot.
Adding a driver must also use a payload for the retained generation; if APK's
solver cannot select it automatically, request its matching tracker version
explicitly. An incompatible request fails before package writes rather than
installing another same-ABI image. Initial migration without an installed image
tracker can still enroll its first versioned kernel.
The APK solver still enforces the exact OpenWrt kernel ABI. Old payloads are
anchored by installed-package checksums;
APK cannot silently replace or remove them. The manager checks the original
kernel, retained payloads, module completeness, built-in features and free space
before activating anything. Disabling scripts/commit hooks is rejected for kernel
transactions. A failed package transaction cannot arm a trial.

Patched APK r9 also checks its minimal self-upgrade phase. If that phase would
change a managed kernel package, it is deferred to the full upgrade transaction,
so a newly enrolled image cannot be installed ahead of its selected modules.
Support-only self-upgrades keep the normal policy checks and behavior.

The manager builds a small matching-module bootstrap initramfs. It mounts the
existing squashfs and hands off to its normal init/fstools extroot path. It does
not replace the root filesystem or systemd with a standalone OpenWrt initramfs.
New boot files go under `/boot/kernels/<generation>/`; GRUB receives separate
systemd, procd and failsafe entries. The original kernel remains untouched.

Reboot deliberately when ready. GRUB clears the one-shot `next_entry` before
trying the candidate; the saved default remains the last confirmed kernel.
Promotion requires 120 seconds of continuous systemd/router health, the same
persistent overlay and LAN addresses, required routes/interfaces, and KVM VM
creation plus libvirt access when KVM was available before the upgrade.

A hard hang requires a reset or watchdog. On the following boot GRUB selects the
old saved default. The user can also select the original or previous kernel from
the menu. A failed health check leaves the old default in place; it does not
force a reboot.

```
kernelctl rollback  # cancel a pending trial, or select previous confirmed kernel
kernelctl retry     # explicitly re-arm a rejected selected candidate
kernelctl retain    # enforce the /boot limit and queue obsolete APK cleanup
kernelctl prune     # synchronously remove withdrawn generations' APK payloads
kernelctl status
```

`kernelctl remove <generation>` explicitly withdraws a nonessential generation
before removing its packages. It refuses the original rescue, running, pending,
known-good and previous-good generations. Retention removes only generations
beyond the trial/fallback pair. If the two protected generations still do not
fit, the space check fails safely rather than deleting either of them.

## Boot and module payload retention

`/boot` keeps at most two versioned generations:

- while a trial is pending: the candidate and the confirmed known-good fallback;
- after promotion: the new known-good and the old previous-good fallback.

The legacy rescue kernel (`/boot/vmlinuz` and the `owrt-rescue*` entries) is not
counted toward the limit and is never removed.

Before a new candidate's boot payload is staged, the manager withdraws every
other generation. It sets `ready: false` in `state.json`, deletes
`/boot/kernels/<generation>/`, and rewrites `/boot/grub/openwrt.cfg` so GRUB no
longer lists that generation. Orphan `/boot/kernels/*` directories (for example
after a manual deletion or an interrupted activation) are removed as well. The
pruning happens before the boot-space calculation, so repeatedly upgrading
kernels cannot exhaust `/boot` by retaining every generation. `kernelctl retain`
runs at boot from `kernel-generation.init` after `prepare`, enforcing the same
invariant after a manual change.

Retention also queues `openwrt-kernel-prune.service` through a path unit. The
worker removes withdrawn generations' immutable kmod, image and header APKs
using `apk del`, then removes manager-created module indexes and frozen firmware
from that generation's trees. Successful cleanup removes the generation record.
Logical kmod selection packages and unrelated userspace packages are preserved.
The rescue, running, pending, known-good, previous-good and selected tracker
generations are excluded, even if their boot payload has been withdrawn. Unknown
module directories and packages without a recorded generation are left alone.

APK hooks only queue this work: they never recursively invoke APK while holding
its database lock. The worker releases the kernel policy lock before invoking
APK. Before preparing that deletion it waits for APK's database lock, so the
original upgrade's post-hook finishes first. It uses a durable deletion plan so
the APK pre-hook rejects solver changes outside the planned obsolete payloads.
Failed or interrupted cleanup restores
checksum protection on retry; no incomplete cleanup makes a generation bootable.
The service retries failures after 30 seconds. `kernelctl prune` performs the
same cleanup synchronously, and `kernelctl remove <generation>` remains available
for explicit removal. APK simulations do not queue or perform cleanup.

## Scope and verification

Rollback covers the kernel, matching modules, frozen firmware and autoload rules.
Userspace, UCI configuration, services, VM definitions and data remain shared.
It does not undo an unrelated userspace upgrade or restore a whole-system
snapshot. Keep independent backups and validate userspace changes separately.

Source tests:

```
PYTHONDONTWRITEBYTECODE=1 python3 scripts/tests/test-kernel-upgrade.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/tests/test-build-and-publish.py
KERNEL_POLICY_APK=/path/to/native/patched/apk \
  python3 scripts/tests/test-kernel-apk-policy.py
```

The C-policy tests use signed disposable root directories and require passwordless
sudo for chroot execution. The serial QEMU controller is
`scripts/tests/kernel-upgrade/vm-console.py`; it always uses qcow2 overlays, an
independent NVMe extroot and isolated user networking. Acceptance must exercise
ordinary signed APK upgrades, candidate promotion, failed-boot fallback, manual
old-kernel selection, module/config retention, native systemd/network/KVM and the
exact freshly built EFI and BIOS artifacts. QEMU proof is not physical-router
proof. The subsequent support-only physical installation is recorded in
[the physical deployment report](kernel-upgrade-physical-20261015.md). It keeps
the original running kernel and does not require a reboot. A later actual kernel
upgrade requires a deliberate user reboot to run the candidate.
