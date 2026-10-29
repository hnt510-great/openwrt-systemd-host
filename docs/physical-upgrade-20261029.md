# Physical upgrade staged for user reboot, 2026-10-29

Upgraded router `192.0.2.1` without rebooting. Installed 131 audited userspace
operations, signed APK support tool `3.0.5-r16`, and 510 kernel operations
covering the image, rolling tracker, 253 logical kmods and their matching
immutable payloads, plus generation-specific development headers.

- Running and known-good: `7.3-owrt-5001c59b1072ebdf1a2ed551a854f37a-r1-g30`.
- Pending next boot: `7.3-owrt-5001c59b1072ebdf1a2ed551a854f37a-r1-g38`.
- GRUB saved entry remains generation 30; one-time next entry is generation 38.
- Original rescue remains `legacy-6.18.55`.
- `kernelctl check` passes; boot ID is unchanged. Physical generation-38 boot
  acceptance is pending the user's reboot.

All incoming kernel snapshot APKs and the signed index matched their published
SHA256 values and verified against the existing router trust. The exact offline
510-operation plan passed twice, with no removals or unrelated userspace changes.
Installed versions and local-file identities match the reviewed signed payloads.
The original boot image/rescue and retained generation-30 boot files keep their
hashes. Normal two-generation retention withdraws generation 25's separate boot
entry; generation 30 is the fallback, and the original rescue stays available.

The existing same-ABI policy prevented even an explicit versioned image request.
The source fix accepts only a direct exact constraint on the newer versioned
image (or its signed local APK), while ordinary tracker/driver upgrades remain
conservative. Protected payload constraints and kernelctl transaction checks
still run. The separately built and signed r16 support tool was installed before
the unchanged VM-validated generation-38 payloads; the previously published
firmware image itself was not rebuilt or replaced for this tool fix.

Twenty-four isolated APK policy tests pass, including explicit local-image
installation, retained old-image pins, ordinary same-ABI upgrades, protected
payload retention, no-script rejection and corrupted-payload rejection. The
corruption fixture now truncates signed content rather than flipping potentially
ignored compression padding. The local-file fixture explicitly enables package
caching, as required for ephemeral test roots.

Backups precede each transaction; independent rollback timers guarded installation
and were cancelled only after acceptance. Userspace pin intent is preserved,
including the audited passt release migration. Existing logical kernel tracker
world entries retain their original unpinned form; immutable generation anchors
are retained. Protected kernel constraints are updated for the new pending trial.

LAN, WAN, WAN IPv6 and WireGuard are up, with IPv4/IPv6 default routes present.
Protected UCI/trust configuration hashes, existing unit PIDs/states and QEMU
processes are unchanged. Only the two pre-existing hostname-sync units remain
failed. No workload or machine reboot was requested by this deployment.

Private receipts, reviewed plans, source/build/policy-test logs and final health
are in `bin/deployment/full-upgrade-20261029/`. Router rollback archives and
staged signed payloads remain under `/root/full-upgrade-20261029/` (root-only).
The host `.config` is unchanged. Source changes are uncommitted and the r16
support-tool hotfix has not been promoted to the public feed.

## Post-reboot prune repair

The physical router booted g38 and confirmed it as known good, retaining g30
as previous good and legacy 6.18.55 as rescue. The prune worker then repeatedly
failed because `apk del` solves directly instead of using the common commit
wrapper that loads protected checksum dependencies. Its proposed deletion
included g30 orphan payloads as well as the withdrawn g25 payloads; kernelctl
correctly rejected that broader transaction before writes.

`0106-openwrt-retain-kernels-on-delete.patch` makes the delete applet load the
same protected constraints before solving. The kernelctl transaction guard is
unchanged. Signed `apk-mbedtls 3.0.5-r17` was built and installed in a one-package,
fully offline simulated transaction with backup and a rollback timer. Installation
was verified and accepted before resuming cleanup. This support-tool hotfix is
installed on the router; it is not part of the original g38 image or a new public
feed publication.

On 2026-10-29 at 15:00:17 +08:00, the prune service completed successfully.
Exactly 253 g25 packages were removed. All g30/g38 package records remained
unchanged, as did the running kernel, boot ID, known-good/fallback/rescue selection,
UCI configuration and trust keys. The protected dependency file changed as expected
when obsolete g25 entries were removed. `kernelctl check` passes, the prune path
is active, no pruning plan/marker remains, and the service reports success with
zero restarts. No router reboot or router/desktop workload restart was performed.

Validation: 25 APK policy tests (including protected orphan preservation during
unrelated deletion), 54 kernel lifecycle tests, target/host APK builds,
`git diff --check`, and checkpatch with zero errors/warnings (ignoring only
MISSING_SIGN_OFF). Private evidence and rollback receipts are in
`bin/deployment/kernel-prune-fix-20261029/` and router staging/backup in
`/root/kernel-prune-fix-20261029/`.
