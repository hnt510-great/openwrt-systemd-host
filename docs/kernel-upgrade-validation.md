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

## Boot payload retention (2026-10-18)

Host, disposable-QEMU, and real generation-upgrade validation of the automatic
`/boot` retention policy. No production feed was modified, no image was flashed,
and the router at `192.0.2.1` was not touched. A g17 generation was built into
an isolated test feed to exercise a real `apk upgrade`; the production feed
remains at sequence 16. The runtime evidence above remains the record for boot,
trial, fallback and rollback behavior.

`kernelctl` now keeps at most two versioned generations in `/boot`: the pending
candidate plus the confirmed fallback during a trial, or the new known-good plus
the old previous-good after promotion. Other generations are marked
`ready: false`, their `/boot/kernels/<generation>/` payloads are removed, and
their GRUB entries are dropped. Pruning runs before the boot-space check, from
the live `apk-pre`/`apk-post` hooks, and at boot through the new
`kernelctl retain` command. APK packages remain installed, and the legacy rescue
kernel is never touched.

The QEMU guest booted the existing signed image
`bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz`
(built 2026-10-18 02:39, before this change) with the modified `kernelctl` and
`kernel-generation.init` injected through a small vfat payload disk. The guest
was rebooted once; the scripts were not packaged into a new image.

| Check | Result |
|---|---|
| `python3 -I scripts/tests/test-kernel-upgrade.py` | 39 tests passed |
| Retention keeps candidate + known-good, withdraws previous-good and extras | Pass |
| Pruning removes `/boot/kernels/<generation>` before the space check | Pass |
| Orphan `/boot/kernels/*` directories are swept | Pass |
| Rejected trial is withdrawn and removed by rollback, even while running it | Pass |
| A running generation within the two slots is preserved | Pass |
| Confirmation keeps exactly the new known-good and old previous-good | Pass |
| Legacy `previous_good` reference is preserved | Pass |
| Simulated APK transactions never prune | Pass |
| Legacy `/boot/vmlinuz` SHA-256 unchanged throughout | Pass |
| `finish_remove` tolerates an already-pruned boot directory | Pass |
| QEMU `kernelctl retain` keeps exactly two fabricated generations | Pass |
| QEMU live `apk-pre` hook prunes and withdraws an extra generation | Pass |
| QEMU `apk-pre` simulation keeps the extra generation | Pass |
| QEMU reboot boot-time `kernel-generation` init prunes two extras | Pass |
| QEMU rescue `/boot/vmlinuz` unchanged and no pending trial after reboot | Pass |
| `git diff --check` | Pass |

### Real g17 generation upgrade (2026-10-18)

To exercise the actual APK kernel transaction path, a g17 generation was built by
temporarily setting `CONFIG_OPENWRT_KERNEL_SEQUENCE=17` and publishing into the
isolated destination `/srv/openwrt-validation/g17-test-feed`. The production feed
(`/srv/openwrt-feeds`, sequence 16) was not modified. `.config`,
`configs/lan-apk-feeds.json` and `tmp/.kernel-publication-inputs.json` were
restored to their sequence-16 state after the build.

The disposable QEMU guest booted the existing g16 image with the modified
`kernelctl` injected, mounted the g17 channel from a vfat payload disk, and ran a
live upgrade against only that repository:

```sh
apk --repositories-file /dev/null \
    --repository /mnt/kerneltest/repo/packages.adb upgrade
```

The transaction upgraded 501 packages (`kmod-*` `1000.16` to `1000.17`,
`openwrt-kernel-upgrade` `1-r14` to `1-r15`, `linux-image-openwrt` `1-r16` to
`1-r17`), installed the g17 image and modules, and selected g17 as the pending
trial. A fabricated extra `/boot/kernels/<generation>` was pruned by the live
`apk-pre` hook; the preceding `--simulate` run left it untouched. The guest was
then rebooted and the 120-second health confirmation promoted g17.

| Check | Result |
|---|---|
| g17 generation published to the isolated feed (509 packages, 1 image) | Pass |
| Production kernel feed still at sequence 16 | Pass |
| Real `apk upgrade` completed (501 packages, exit 0) | Pass |
| Live `apk-pre` pruned the fabricated extra generation | Pass |
| `apk upgrade --simulate` kept the extra generation | Pass |
| g17 became the selected pending trial after the upgrade | Pass |
| Rebooted guest ran `…-g17` and promoted it to `known_good` | Pass |
| Legacy g16 rescue retained as `previous_good` | Pass |
| `/boot/kernels/` contains only g17; legacy payload remains `/boot/vmlinuz` | Pass |
| Rescue vmlinuz hash unchanged; `kernelctl check` passes | Pass |

The source image's g16 kernel is adopted as the legacy rescue on first boot, so
this first versioned upgrade legitimately has one `/boot/kernels/` directory plus
the legacy rescue. The earlier QEMU retention run covers the steady-state case
with two versioned `/boot/kernels/` directories.

Evidence:

- `/srv/openwrt-validation/g17-test-20261018/build-g17.log`
- `/srv/openwrt-validation/g17-test-feed/public/kernel-upgrades` (sequence 17)
- `/srv/openwrt-validation/qemu-kernel-retain-20261018/run_g17_upgrade_v3.log`
- `/srv/openwrt-validation/qemu-kernel-retain-20261018/run_g17_verify.log`
- `/srv/openwrt-validation/qemu-kernel-retain-20261018/vm-g17/serial.log`

The host tests are reproducible with the command above. No physical device was
flashed or touched for this change.

### Packaged current-image retention (2026-10-18)

The 17:38 EFI image was tested directly in an isolated QEMU/KVM guest with a
disposable qcow2 overlay. Its SHA-256 was
`b438fde98cf07e7fffd96af8941cc293a82d69ed914dffb40b5047ef640bc7a4`.
The built-in `kernelctl` and `kernel-generation` init hashes matched the source;
neither production script was injected or replaced.

All 39 host tests passed. With additional generation records and boot directories
created as test fixtures, `kernelctl retain` kept exactly two generations and
withdrew the extra GRUB entries. A real signed APK simulation left state and
directories unchanged. Reinstalling `linux-image-openwrt` `1-r17` then triggered
automatic pruning through the live APK hook with the original health checks.
After reboot, the packaged boot service pruned additional fixtures and kept the
two selected generations. The rescue kernel hash remained unchanged and
`kernelctl check` passed. The genuine baseline state was restored and the VM
stopped; the original compressed image hash remained unchanged.

This run tested a current-generation tracker reinstall, not a cross-generation
upgrade or boot into a new kernel. It did not access the physical router or
remove installed APK/module payloads. Evidence, the image receipt and test
scripts are retained under
`/srv/openwrt-automation/image-autoprune-20261018T181813/`.

### Skip same-ABI publication generations (2026-10-18)

APK `3.0.5-r11` retains the installed image, logical module and header trackers
when only the publication generation increases at the same exact OpenWrt ABI.
The earlier same-ABI cross-generation upgrade results above predate this policy;
such upgrades are now intentionally skipped on an enrolled installation.

Validation completed:

- `make package/system/apk/compile -j8 V=s`: passed, producing
  `bin/systemd/packages/x86_64/base/apk-mbedtls-3.0.5-r11.apk`.
- `test-kernel-apk-policy.py`: 14 tests passed with an isolated native build of
  the patched APK, signed fixture repositories and disposable roots/chroots.
  Coverage includes simulation, real userspace updates without kernel changes,
  targeted image/module upgrades, matching-generation driver installation,
  preservation of explicit world constraints, and a later ABI transition whose
  hash sorts below the installed hash. Temporary retention pins do not enter
  `/etc/apk/world`.
- `test-kernel-upgrade.py`: all 39 tests passed.
- Checkpatch (`--no-tree --no-signoff`) and `git diff --check`: passed.
- `.config` SHA-256 remained
  `c48968d91c5fb959f21be2d23bc2d06e63461183d4910fb5e4e92e07c0e8d9af`.

Build and test logs are in `/tmp/openwrt-abi-policy.p863BX/`. This change has
package-build and isolated transaction coverage; no new firmware image was
built or booted in QEMU, and no feed publication or physical-router deployment
was performed.

#### Subsequent signed publication and physical deployment

Published `apk-mbedtls-3.0.5-r11.apk` to the running router ABI's `base` feed
and the kernel channel. Publication added only this support package; all prior
APK hashes, 11 kernel images and channel sequence 18 were retained. APK SHA-256:
`d30bf91f5c99ab8506fc5a70da1eb5f5ba632558452a72376ae50f8571b22e5f`.

On the physical router, existing trust verified the package and a signed
single-package offline index. Simulation and installation both selected only
`apk-mbedtls`, upgrading `3.0.5-r10` to `3.0.5-r11`. The old APK added 250
existing protected-payload constraints to world during self-upgrade; only those
new entries were withdrawn to restore the exact original world. The separate
protected dependency file was unchanged.

The installed tool skipped a synthetic same-ABI G19 candidate in a private,
simulation-only repository, printing `Keeping installed kernel generation: ABI
unchanged.` No package writes occurred; the test used a temporary signing key
and did not alter global trust or publish the candidate. The remote test
repository was removed afterward. `kernelctl check`, `apk update` and simulation
against the production feeds then passed; the production simulation selected
no upgrades.

Final comparison confirmed that only the APK tool's installed record changed.
The router remained on G18 with the same boot ID, no pending kernel trial,
unchanged kernel/GRUB/policy/configuration files and world, three active router
service units, and no failed systemd units. No reboot was performed.

Evidence: `/srv/openwrt-validation/apk-abi-policy-deploy-20261018T112854Z/receipt.json`.
The root-only remote backup is
`/root/apk-abi-policy-deploy-20261018T112854Z/`.

## IPv6 logging compatibility tracker, 2026-10-23

Upstream commit `313889ee5c` removed the empty `kmod-nf-log6` package. The
physical router still selected it in world on g23, while the signed channel
offered g25 with ABI `6.18.55~99d816e22a3cf14cc4aad935e110f3ea-r1`. Ordinary
upgrade simulation failed because the remaining g24 `kmod-nf-log6` tracker
required the old ABI. `--prune` could not help while the old ABI repositories
still supplied that name. A simulation excluding the package also hit the
kernel policy's selected-module removal protection.

The fix retains a hidden, default-selected compatibility tracker for kernel
generation builds. It depends on `kmod-nf-log`, adds no Kconfig symbols or module,
and receives the normal immutable generation metadata. A regression test scans
the real recipe without `.config` and checks that the conditional Kconfig
default survives package metadata generation.

Source/package checks passed: 53 tests in `test-kernel-upgrade.py`,
`git diff --check`, and a recipe build of the g25 tracker and generation payload.
Both APKs and their temporary index passed signature verification on the host
and against the router's existing trust. The signed publisher dry run accepted
only these two additions, yielding 1,029 packages and retaining g24 and g25.
No existing published artifact was replaced and the active manifest was unchanged.

With only that temporary local repository added, physical-router
`apk upgrade --simulate` exited 0 with 523 changes, including upgrading
`kmod-nf-log6` from `1000.23.6.18.55-r1` to `1000.25.6.18.55-r1` and installing
its g25 payload. The real kernel policy hooks accepted the transaction. This
was a simulation with repository access, not an offline installation or boot
test. No VM validation was performed.

The router's world and installed-database SHA-256 values, boot ID, known-good
g23, previous-good g21, ready phase and empty pending trial were unchanged.
The working `.config` hash was unchanged. The temporary router repository was
removed. Publication, package installation and reboot were not performed.

Local review evidence and the two signed APKs are under
`tmp/nf-log6-compat-20261023/`, including `sha256.json`, `router-simulate.log`,
`router-state-after.txt` and `publisher-dry-run.log`.

## Installed-system upgrade preflight, 2026-10-24

The publisher now stages both signed views once, validates the configured live
router's upgrade, binds the baseline/policy/index/APK hashes, and promotes those
same snapshots. Direct production low-level publication is rejected. Empty
compatibility rules use a central registry and the normal kernel package
splitter. The registry invalidates metadata scanning and kernel input hashes;
an unnormalized existing `.config` still builds the channel compatibility APK.

`apk-mbedtls` 3.0.5-r13 was built with the new full-transaction preflight,
`--userspace-only` and `--plan-json`. It selects a newer ABI candidate explicitly
for an ordinary managed full upgrade while retaining explicit world/tag pins.
Solver-only protection constraints are not saved into world. Remote, cached
and local payloads are authenticated before managed package writes.

Source/build checks passed:

| Check | Result |
| --- | --- |
| Kernel manager and actual recipe metadata tests | 54 passed |
| Signed build/publication and failure-isolation tests | 47 passed |
| Native patched APK tests in disposable chroots | 21 passed |
| Baseline/migration/receipt preflight tests | 17 passed |
| LAN publisher tests | 20 passed |
| Scheduled-maintenance tests | 17 passed |
| `checkpatch.pl --no-tree --no-signoff` on the APK patch | 0 errors, 0 warnings |
| Top-level `prepare-tmpinfo`, generated compatibility metadata, `.config` hash | Pass |
| `git diff --check` | Pass |

The 176 tests include the removed-name failure, unknown removed modules, real
files rejected by empty migration rules, missing replacement/payload, target-ABI
userspace conflicts, baseline races, altered prepared bytes, bin changes after
validation, second-pointer failure/rollback, same-ABI retention, explicit pins,
preupgrade blocking and corrupt local-payload rejection before package writes.

A disposable EFI/KVM overlay of the existing g23 image installed the signed APK
and exercised missing-migration, userspace-only and compatibility-success
transactions in an isolated package root. Those synthetic transaction cases use
a static test policy helper; real `kernelctl check`, the VM's actual kernel state
and SSH service were checked separately. The VM rebooted on its existing g23
kernel with r13 installed and no pending trial. The exact installed executable
after reboot matched the final signed APK's extracted executable SHA-256:
`6105c3e76827ecd448bb5738b3e006a582136593d2cd55e22ac9bcaa5c399874`.
The synthetic cases also passed after reboot. The disposable VM was shut down.

The old r11 bootstrap process appended 253 existing protected constraints to VM
world while first installing the new APK. Only those independently audited new
entries were removed to restore the captured world. The subsequent r13 upgrade
preserved world, protected constraints and kernel state without cleanup. This
is the one-time bootstrap behavior described in `apk-upgrade-preflight.md`.

The full production dry run used the actual router's r11 APK and real policy
hooks, exiting successfully with the final r13 staged candidate. Both production
aliases remained at their original targets. During this work the router also
received a separate nine-package QEMU/base-files update; its world/database
therefore differ from the initial capture. Each preflight window was internally
stable and the final router state matched the final successful preflight.
The running g25 ABI, boot ID, kernel-policy state, protected constraints and APK
binary were unchanged. The separate update was preserved.

Final signed APK SHA-256:
`3ad4e5a3e5d47480c50fb0b0364e168b6e8276c233aa5617a1cffd8726e4da3b`.
No production publication, physical package installation or physical reboot was
performed. No full replacement firmware image or real new-kernel boot was tested
for this change. Evidence is in `tmp/apk-upgrade-guard/`, especially
`validation-summary.json`, `final-audit.json`, `production-preflight-r13.json`,
`vm-r13-validation.log`, `vm-fixture-receipt.json`, and `vm-after-reboot.log`.

## Authorized publication and physical installation, 2026-10-24

Following explicit authorization, the coordinated publisher exposed the tested
userspace and kernel-channel snapshots. The only changed userspace package was
`apk-mbedtls` 3.0.5-r13; there were no same-version rebuilds. The channel retained
g24/g25 and did not advance the kernel generation. Signature verification and
an HTTP download from the formal ABI feed matched the validated APK SHA-256
`3ad4e5a3e5d47480c50fb0b0364e168b6e8276c233aa5617a1cffd8726e4da3b`.

The physical router's exact existing r11 executable was matched to the retained
signed r11 APK. A private root-only backup captured the executable, APK database,
world, kernel policy, repository/configuration state and GRUB state. A temporary
signed single-package offline index simulated exactly one change, r11 to r13.
The identical published payload was then installed offline under an independent
ten-minute systemd rollback timer. No unrelated package was upgraded.

Acceptance passed:

- The installed executable matched the final signed payload SHA-256
  `6105c3e76827ecd448bb5738b3e006a582136593d2cd55e22ac9bcaa5c399874`.
- All 1,767 installed package identities were compared by name; only
  `apk-mbedtls` changed. World was preserved byte-for-byte. The r11 process added
  no new protected-world entries in this transaction.
- Running g25 ABI, boot ID, protected constraints, kernel state, GRUB and
  network/SSH configuration hashes were unchanged. No reboot was performed.
- `apk update`, ordinary upgrade simulation and explicit userspace-only
  simulation passed. Both schema-1 JSON plans reported zero changes and were
  written with mode 0600. `kernelctl check` passed, SSH was active, LAN/WAN were
  up and systemd had no failed units. HTTPS served the normal LuCI login form
  with its unauthenticated HTTP 403 response.
- After acceptance, the rollback timer was stopped. A fresh coordinated
  production dry run used the installed r13 client, consumed its native JSON
  plan and passed with zero changes; both published views were unchanged.

Deployment evidence is in `tmp/apk-upgrade-guard/deploy-20261024/receipt.json`
and its adjacent publication, offline simulation, installation, acceptance and
post-install preflight logs. The retained root-only router backup is
`/root/apk-upgrade-guard-20261024.Euocjs/`.

## Interrupted first-boot adoption, 2026-10-31

A reboot during the first boot of the g42 image interrupted adoption while it
copied the legacy modules. Version 1-r17 then failed on every boot with
`Incomplete adoption exists; inspect before retrying`, and APK refused
transactions that needed adoption. Version 1-r18 discards the copies made
before `state.json` exists and restarts adoption; resumed `adopting` phases now
rewrite `legacy-release` and the APK pins. kernelctl exits through Python
cleanup on SIGTERM.

The kernel-upgrade suite passed 58 tests, including four new cases: restart
after interrupted copies; refusal with leftovers preserved after the GRUB
dispatcher, a differing rescue snapshot or APK pins; resume after the state
save; and SIGTERM cleanup. Against 1-r17, the restart, resume-order and SIGTERM
cases fail, and the restart case fails with the router's message.

Disposable KVM/UEFI VMs booted the published g42 image
(SHA-256 `2fee3574e9f975e96ba2c522a59f4bb098ba4a5b0476bf71ad26acfb431389f9`)
on fresh overlays:

| Check | Result |
| --- | --- |
| Reboot 1 s after the 1-r17 boot unit started copying | No `state.json`; leftover legacy tree, `.firmware-*` staging and `grub.cfg.rescue` |
| Next boot with 1-r17 | `Incomplete adoption exists`; boot unit failed; system degraded |
| Install 1-r18 `kernelctl`, start the boot unit | Copies discarded; phase `ready`; `kernelctl check` passed; rescue dispatcher installed |
| Following reboot | System running; boot unit succeeded; no failed units |
| Separate run: 1-r17 interrupted after the state save, 1-r18 next boot | `adopting` resumed in 2 s; phase `ready` |
| APK after adoption | `openwrt-kernel-upgrade` 1-r18, `systemd-openwrt` 13 and `systemd-openwrt-services` 4 installed together |

The serial controller becomes available after the boot unit starts, so a
first-boot interruption of 1-r18 itself was not reproduced in a VM; the unit
tests cover it. This is VM validation; no physical device was flashed.
Evidence: `bin/validation/sync-20261031/kernel-adoption/`.

## Same-ABI generations installed by default, 2026-11-02

**Superseded before publication.** Kernel packages
([kernel-upgrade.md](kernel-upgrade.md)) replaced per-generation payloads on the
same day. APK patch 0107, the `same-abi-hold` switch and the `trial-pending`
marker were removed; apk `3.0.5-r18` and `openwrt-kernel-upgrade 1-r19` as
described below were never published. The record is kept for history.

APK `3.0.5-r18` adds `0107-openwrt-upgrade-same-abi-kernels.patch`. A full
`apk upgrade` now installs a newer `-gN` generation at the identical ABI when
the solution carries every payload kernelctl requires (`<name>-<generation>` for
each installed logical `kmod-*` and for `kernel-dev-headers`). It keeps the
installed generation, as before, when `/etc/openwrt-kernel/same-abi-hold`
exists, when `/etc/openwrt-kernel/trial-pending` exists, for targeted upgrades
and module additions, and when a payload is missing. `openwrt-kernel-upgrade`
`1-r19` maintains `trial-pending` from `state.json` and adds
`kernelctl same-abi-upgrades enable|disable|status`. It requires
`openwrt-kernel-policy >= 3.0.5-r18`. The publication baseline hashes the hold.

| Artifact | SHA-256 |
| --- | --- |
| `bin/systemd/packages/x86_64/base/apk-mbedtls-3.0.5-r18.apk` | `6b57efc8046740ce2de0ab5e86d9c58b329c0452fa2d587d9b59fd14fe2950ca` |
| `bin/systemd/packages/x86_64/base/openwrt-kernel-upgrade-1-r19.apk` | `38faa5932bc380733e7099fe8285cf761a87e0d9f968c3569451a49be990988d` |

| Check | Result |
| --- | --- |
| `make package/system/apk/compile`, `make package/custom/openwrt-kernel-upgrade/compile` | Passed; no `commit.c` warnings |
| Existing 25 APK policy tests against r18, before test changes | 22 passed; the 3 full-upgrade keep tests now upgraded, as intended |
| Native patched APK policy tests in disposable chroots | 29 passed |
| Default full upgrade, g10 to g11 | Tracker, kmod and header trackers and all three g11 payloads installed; g10 payloads retained; world unchanged; kernelctl transaction lists the new image |
| Hold set | `Same-ABI kernel upgrades are held`; g10 kept; userspace upgraded; world unchanged; a later ABI transition still upgrades |
| `trial-pending` present | g10 kept; userspace upgraded |
| g11 published without its header tracker and payload | `lacks kernel-dev-headers-...-g11`; g10 kept; userspace upgraded |
| g11 header tracker published without its payload | Solve fails with the hold set as well; this predates r18 and the publication preflight catches it |
| Targeted `apk upgrade linux-image-openwrt` or `kmod-*`, `apk add` of a new module | Installed generation kept (existing tests, no hold) |
| Explicit exact image request while held | Installed |
| `test-kernel-upgrade.py` | 62 passed: marker on arm, removal on rollback and promotion, marker kept when the state write is interrupted, switch enable/disable/status |
| `test-apk-upgrade-preflight.py` | 29 passed: the real `BASELINE` script records the hold, and toggling it changes the baseline |
| Build/publication, LAN publisher, source-version, ELF ABI and needrestart suites | 59, 26, 2, 23 and 91 passed |

Scope: host and chroot tests with a native build of the patched APK. No kernel
generation, image or VM upgrade was exercised with r18. Nothing was published,
and no router was contacted or changed. needrestart still reports an armed
same-ABI trial as `optional-same-abi-trial`.
Evidence: `/srv/openwrt-validation/upstream-update-20261102T023631Z/same-abi/`.
