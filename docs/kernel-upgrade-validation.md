# Kernel upgrade validation

Validation workspace: `/srv/openwrt-validation/kernel-upgrade-validation-20261015`.
The initial validation below performed no physical router deployment, flashing,
reboot, bridge attachment, or LAN feed publication. The later support-only
physical installation and LAN publication are recorded separately in
[the physical deployment report](kernel-upgrade-physical-20261015.md).
QEMU used disposable qcow2 disks, an independent NVMe
extroot, and restricted user networking. Existing host VMs were left running.

## Combined build/publish follow-up, 2026-10-16

`./scripts/build-and-publish.sh -j16` now reserves an unused generation when
kernel inputs change, forwards make arguments, and publishes both userspace and kernel
channels after success. `publish-changed-feeds.sh` shares the same publishing
path without advancing the sequence. Published legacy ABI-local kernel files
are retained; new generation trackers/payloads are supplied through the kernel
channel. Both publishers preflight before the userspace view is exposed, and
the kernel channel is exposed last. Repeating an unchanged publication creates
no new active snapshot. Neither wrapper deploys to a router.

Validation of this host-script follow-up:

- `test-build-and-publish.py`: 20 passing tests with actual signed APK fixtures.
  These cover generation selection with stale output present, same-ABI legacy
  package preservation, a lower-sorting new ABI with the old router feed intact,
  retained generations/snapshots, empty signed ABI views, signature failures in
  either channel, missing module payloads, altered published payloads, stale
  generations, sequence reservation/retry/overflow, make failure/argument
  forwarding, and publication ordering after successful make.
- `test-lan-apk-publisher.py`: 13 passing regression tests.
- `test-kernel-upgrade.py`: 29 passing regression tests.
- Shell syntax, Python syntax and `git diff --check` pass.
- The actual shell entrypoint rejects a make preview without changing `.config`
  or the live LAN aliases.
- The integrated `publish-changed-feeds.sh --source-root .../tree --dry-run`
  succeeds with the complete G3 build, including stale experimental kernel
  outputs. The kernel channel reports 509 unchanged packages; the existing
  userspace view previews 1268 packages. No live publication alias was changed.
  Logs are in `physical-feature-20261015/` beneath the validation workspace.

This follow-up did not run a new full firmware build, change physical-router
packages, or reboot the router. Earlier firmware/QEMU acceptance below remains
the artifact-specific runtime evidence.

### Input-based sequence optimization

The subsequent optimization records relevant source/config/tool input hashes in
`tmp/.kernel-publication-inputs.json`, rather than advancing on every full build.
Unchanged inputs reuse the generation and a pinned kernel build timestamp;
ordinary userspace source/version/selection or commit timestamp changes do not
force a new kernel. Kernel patches, same-ABI module source changes, selected module
options, package kernel-config requests, build tools and explicit kernel flags do.
The first build without a local record uses a conservative unused generation.
Identical-input failure retries retain the reserved generation and timestamp.

The input optimization is exercised by the expanded combined publisher tests,
including a successful signed userspace update through two complete mocked make
invocations with the same kernel channel, a failed build followed by a same-sequence
retry, and source changes during make being blocked before publication. These
tests use actual signed APKs; make is mocked so no whole-firmware build or physical
deployment is implied. Read-only fingerprinting of the actual main checkout also
confirmed that changing a Weston package selection leaves the fingerprint intact.
The final optimization run passed 37 combined publisher tests, 13 legacy LAN
publisher tests and 29 kernel-upgrade tests (79 total). The combined tests also
cover effective module-version changes, generation numbers embedded in metadata
being excluded as decision inputs, and the pinned timestamp across different
userspace commit epochs. Logs are in `sequence-optimization-20261016/` beneath
the validation workspace. Python/shell syntax and `git diff --check` passed.

## Implemented delivery

During initial validation, the feature was opt-in through
`OPENWRT_KERNEL_UPGRADE`; the main tree's `.config` and original firmware image
were preserved. The subsequent requested change enables it by default and sets
the working/desktop configurations to publication sequence 4. The validation
builds used an isolated worktree and
copied staging/build caches. The original APK signing identity was retained. The isolated configuration enables
both GRUB firmware variants and kernel publication sequence 3.

The exercised transition keeps Linux 6.18.55 and changes the configuration ABI:

| Role | Identity |
| --- | --- |
| Original kernel | `6.18.55` |
| Original ABI | `6.18.55~f10b60a7da5b97b579b974213f7b729c-r1` |
| Candidate release | `6.18.55-owrt-3099baa9ab7a5ed3ea226a586fba0edc-r1-g3` |
| Candidate ABI | `6.18.55~3099baa9ab7a5ed3ea226a586fba0edc-r1` |

The configuration change disables printk timestamps for the test. It deliberately
makes the new ABI hash sort below the old hash, exercising the rolling tracker's
monotonic publication sequence. All 248 installed logical kmods have matching
candidate payloads, including external wireless and button modules. Prepared
headers are versioned and the original headers remain available after migration.

## Source and package checks

- `test-kernel-upgrade.py`: 29 passing tests covering real signed payloads,
  co-installation, ABI ordering, immutable package releases, ownership/modes,
  failed activation, fallback protection, space exhaustion, interrupted activation,
  native-image autoload, persistent overlay requirements, and explicit removal.
- `test-kernel-apk-policy.py`: 7 passing tests using the actual patched native APK
  in disposable roots/chroots. These cover checksum retention, legacy module and
  header preservation, preflight refusal before writes, disabled scripts,
  simulation, transaction errors, and the `--root /` adoption bypass.
- Shell/Python syntax and `git diff --check` passed.
- Kernel compilation, in-tree and external module packaging, target APK/ubox,
  both GRUB platform packages, systemd integration, headers, root filesystem and
  EFI/BIOS image construction passed.
- A real configuration transition exposed an early Make expansion of the ABI
  hash. Kernel release evaluation now waits until configuration is complete;
  actual compiled module vermagic is checked before signing.
- GRUB runtime modules retain their exported ELF symbols. They are not processed
  by the Linux-module stripping routine.

These are targeted build checks, not a complete clean toolchain rebuild. The
existing Weston/Xwayland and WeeChat recursive Kconfig dependency diagnostics
remain outside this change; `make defconfig` can report them while exiting zero.

## Clean installation runtime evidence

`vm-clean-final/serial.log` and `clean-*.log` record a fresh copy of the original
firmware with a newly formatted NVMe extroot. It received signed support packages,
ran `kernelctl migrate`, then ordinary `apk update`, `apk upgrade --simulate`, and
`apk upgrade`, without ABI forcing or untrusted packages.

The real upgrade completed 501 package operations, installed root-owned generation
payloads, preserved the original `/boot/vmlinuz`, network and fstab hashes, and
armed only `next_entry`; `saved_entry` remained the original rescue kernel.

A deliberate `rdinit` stall was injected only into the candidate's GRUB entry.
After a QMP reset of that disposable VM, GRUB booted the original kernel. Native
systemd, router services, SSH networking, KVM VM creation, original headers and
kernel/module integrity checks passed. `kernelctl rollback` and `retry` removed
the injected argument and re-armed the original candidate files.

The normal candidate then booted the existing immutable root and NVMe extroot,
passed the full baseline health interval, and became the saved default. GRUB
menu key selection of the original kernel also booted successfully while keeping
the candidate as the saved default. Original configuration/kernel hashes and
old-kernel KVM creation passed again.

The APK transaction reported sysctl utility write warnings from package scripts;
APK returned success and the preserved/current network, firewall, services and
KVM checks passed. This change does not repair unrelated utility behavior.

## Artifact and firmware coverage

Firmware images are built under
`tree/bin/systemd/targets/x86/64-glibc/`; hashes are in
`final-artifacts.sha256`. Final EFI SHA-256 is
`350b87a02e555a1100a689b95b4fb0f31ba804137a94c956982560f3d51b159a`;
BIOS SHA-256 is
`87c3bf571adabd5fb6735c2c1d9114e731c79a7e6f226c25a72afef630ccc18a`. The validated signed channel is
`validated-channel/public/kernel-upgrades/` (509 packages, one generation); it
has not been served to the LAN. It contains the latest support versions only. Earlier experimental channels are
also retained as test evidence and are not deployment instructions.

Fresh EFI and BIOS image tests verify native systemd, persistent F2FS overlay,
automatic adoption, module integrity, KVM VM creation, and complete generation
autoload rules after another boot. The upgraded disk is also cloned with QEMU
off and tested under BIOS, exercising its runtime GRUB modules and trial path. Final
manager version is `1-r12`; target APK is `3.0.5-r7`. Exact release-image boot
checks are in `vm-release-efi-g3/serial.log` and `vm-release-bios-g3/serial.log`.

The original firmware's SHA-256 before/after is
`de6d2aa35bdd37ab7509612539f28cc3427e4a75874ca9e7b280beb6f03147de`.
The original bootable kernel in the migration VM remains
`1e222b7aa6b7ec4df447c095ce3c6760216ec8e33e7cc18f57f08a5440cc9909`.

Rollback shares userspace and configuration. These tests establish the exercised
kernel/module/GRUB and service behavior in QEMU; they do not certify physical
NICs, storage controllers, GPUs, every installed service, or arbitrary future
userspace upgrades. Physical acceptance remains a separate deployment step.

## Support package publication repair (2026-10-16)

The main-tree G5 build completed but publication correctly rejected
`apk-mbedtls-3.0.5-r7.apk`: its signed bytes differed from the published r7.
Recursive APK metadata comparison found identical program/script contents and
dependencies, with directory/file ACLs changing from `0775/0664` to `0755/0644`.
Seven other support packages also conflicted; `grub2-editenv` additionally had a
different executable hash. Published filenames remain immutable.

The support releases were increased to APK r8, ubox r4, systemd-openwrt 7,
kernel manager 1-r13, LAN feeds 3, and GRUB r5. The combined build wrapper now
runs make with umask `022`; support collisions explain the required release
bump without weakening kernel payload checks.

The six source packages were rebuilt with `-j16`, retaining G5's recorded kernel
build timestamp. All 504 recorded kernel-related APKs, the compiled kernel,
kernel release and working `.config` retained their SHA-256 values. Eight rebuilt
channel support APK signatures passed verification. The 39 build/publication,
29 kernel-manager and 13 LAN-publisher tests passed, including regression cases
for an invoking shell with umask `002` and for preserving a published support
blob while adding its next release.

Publish-only preflight and actual publication then succeeded for
`6.18.55-owrt-f10b60a7da5b97b579b974213f7b729c-r1-g5`. The active channel contains
1,018 packages and both G3 and G5. All 509 previously published package hashes
remain identical in both the new channel and original snapshot, whose manifest
and index hashes also remain identical. The new index signature passed, and its
SHA-256 matched the index served over LAN HTTP. The ABI-specific userspace view
was published first. No additional kernel generation was reserved by this retry.

Evidence is under
`/srv/openwrt-validation/kernel-upgrade-validation-20261015/support-publication-fix-20261016/`.
This was a support-package rebuild and feed publication repair, with no new
firmware image build or physical-router installation/reboot. Earlier QEMU
evidence above applies to G3; G5 has not been boot-tested by this repair.

## APK self-upgrade transaction repair (2026-10-16)

The physical router's ordinary `apk upgrade` failed during `Preupgrading` with
`Transaction lacks matching payload for kmod-9pnet`. Explicit
`upgrade --preupgrade-only --simulate` reproduced the failure. Its minimal
transaction selected APK r8 and the enrolled G6 image/rolling tracker, but kept
the old same-ABI logical modules. The full upgrade simulation already contained
the matching module payloads. The module-completeness guard correctly stopped
the partial transaction before package installation.

APK r9 now defers a minimal preupgrade whenever it would change managed kernel,
image, module or header packages. The ordinary full solver then resolves the
complete set under the existing retention and activation checks. Support-only
preupgrades keep their existing behavior. A signed disposable-root regression
failed on the old binary and passed after this change, including an actual
ordinary upgrade inside a chroot without `--root`, which exercises automatic
preupgrade. All nine C-policy integration tests pass.

The target APK was rebuilt, signed and published without advancing G6. All 508
recorded kernel/config artifact hashes stayed identical. The three existing
published images and all 1,518 existing channel packages were retained unchanged;
the new channel adds only APK r9. The old snapshot manifest and new index
signature were verified.

The signed target binary passed explicit preupgrade and complete upgrade
simulations on the physical router. Only `apk-mbedtls` was then installed,
upgrading r7 to r9 in a separately simulated offline transaction. For this
support-only bootstrap, the uninstalled `linux-image-openwrt` enrollment was
temporarily excluded from world and restored byte-for-byte in a finally block.
Every installed kernel/module constraint and policy hook remained active; the
simulated transaction was required to change only APK before it was executed.
All 426 captured kernel/module, GRUB, UCI/libvirt, manager-state and boot-ID file
hashes matched afterward, and `kernelctl check` and native router service checks
passed. The original kernel remains the confirmed default, with no pending
candidate and no reboot or full kernel upgrade performed.

Evidence and the exact bounded bootstrap script are under
`/srv/openwrt-validation/kernel-upgrade-validation-20261015/preupgrade-fix-20261016/`.
The root-only physical backup is `/root/kernel-preupgrade-fix-20261016T021302/`.

## Physical G7 boot acceptance

The user subsequently upgraded and rebooted the physical router. Read-only
verification confirmed successful G7 boot and health promotion, complete matching
module payloads/vermagic, native systemd/network/KVM operation and preservation of
the original bootable kernel. Exact checks, evidence and the untested physical
failed-boot/guest-OS boundaries are recorded in
[the physical deployment report](kernel-upgrade-physical-20261015.md#subsequent-physical-g7-acceptance-2026-10-16).
