# Interrupted APK transaction validation

Implementation and host validation: 2026-11-12, in this checkout. Evidence is
under `/srv/openwrt-validation/apk-transaction-validation-20261112/` (kept outside
the repository). An exact image was built (build-only, kernel generation 61)
and tested in a disposable KVM guest. At the user's request the build was then
published and the feature was installed on the physical router (see "Publication
and router install"); no firmware was flashed.

Guide: [apk-transaction-recovery.md](apk-transaction-recovery.md).

## Artifacts

| Artifact | SHA-256 |
| --- | --- |
| `apk-mbedtls-3.0.5-r18.apk` (target, not published) | `e1b4ed78b2346e78a8d5e7b7d6656eca742666c7c6c63e1ef5c7c13b217450b7` |
| `apk-transaction-guard-1-r1.apk` (not published) | `4ecb7c0b93d7662f637ab4f72e376eb74896c35c2adc0393d7bdd31ddf591d16` |
| `staging_dir/host/bin/apk` (host build used by the tests) | `6faebe730525cf285d4d4b1e1ffb9ef038f95aeaadbef19e66e35deaa71400f6` |

## Host checks

| Check | Result |
| --- | --- |
| `make package/system/apk/host/{clean,compile} V=s` | Pass; patches 0001–0108 apply in order |
| `make package/system/apk/{clean,compile} V=s` | Pass; `apk-mbedtls-3.0.5-r18` provides `apk=3.0.5-r18` and `openwrt-kernel-policy=3.0.5-r18` |
| `make package/custom/apk-transaction-guard/compile V=s` | Pass; depends on `apk>=3.0.5-r18`; installs `apk-resume`, the rc script, the systemd unit and its `multi-user.target.wants` link, and commit hook `00-transaction-scope` |
| `python3 scripts/tests/test-apk-transaction-journal.py` | 9 tests pass (`test-journal-sh.log`) |
| Same with `APK_RESUME_SHELL='busybox ash'` | 9 tests pass (`test-journal-ash.log`) |
| `KERNEL_POLICY_APK=…/staging_dir/host/bin/apk python3 scripts/tests/test-kernel-apk-policy.py` | 25 existing tests pass with the r18 APK |
| `python3 scripts/tests/test-apk-upgrade-preflight.py` | 37 tests pass, including the new interrupted-transaction baseline refusal |
| `python3 scripts/tests/test-custom-package-updates.py` | Pass with the new `local` registration |
| `systemd-analyze verify apk-resume.service` (host) | Only complaint: `/usr/sbin/apk-resume` is absent on the host |
| Commit hook against the host's systemd 262 as root (`scope-hook-host.log`) | Calling process moved into `apk-transaction-<pid>.scope`; a `shutdown:sleep` **block** inhibitor "Package transaction in progress" registered; both units were gone after the process exited |
| `make defconfig` after merging `configs/apk-transaction-guard.config` | Working `.config` differs only by `CONFIG_PACKAGE_apk-transaction-guard=y`; the desktop snapshot got the same single line, with its pre-existing drift left alone |
| `git diff --check` | Pass |

The journal test runs the patched APK as root in disposable `--root` trees with
`APK_OPENWRT_JOURNAL=1`. It uses signed fixture packages (`alpha` → `beta` →
`gamma` upgraded, `obsolete` removed). A static helper serves as every
maintainer script and commit hook and signals its parent APK at a chosen
point. It covers:

- **Clean upgrade:** no journal remains.
- **SIGINT, SIGHUP and SIGTERM** raised from a `post-upgrade` script: APK
  prints the deferral notice, finishes all four changes, writes the database
  and exits 130, 129 and 143. No journal remains.
- **SIGKILL after the first package:**
  - the journal exists in phase `files`, mode 0700, with `payloads 1`, the
    target world and four `change` lines, including the removal;
  - the database still lists the old versions while `alpha`'s file is
    already new;
  - `apk add` is refused with the "interrupted" message, and
    `apk-resume --status` exits 1;
  - after the **original repository is deleted**, `apk-resume` finishes
    offline from the journal copies: every package is upgraded, `obsolete` is
    removed, the post-commit hook runs and the journal is gone.
- **SIGKILL from the post-commit hook** (database already written): resume
  runs only the post-commit hook. With an `/etc/openwrt-kernel/protected`
  file and a `kernelctl` stub, it recreates `/run/openwrt-kernel-apk.txn`
  with the journaled change lines and runs `kernelctl apk-post` once.
- **Installed database changed after the interruption:** `apk-resume` refuses
  ("changed outside") and keeps the journal.
- **SIGKILL during a resume:** the journal stays, `attempt` becomes 1, and a
  second `apk-resume` completes.

## Exact-image VM gate

| Item | Value |
| --- | --- |
| Image | `image/openwrt-x86-64-generic-squashfs-combined-efi.img.gz` (frozen copy of the build-only output) |
| Image SHA-256 | `663525c5b4f0779c7d8faa83f5ce6e9a1fa795b581327306dc07a5170cfcc15a` |
| Image contents | `apk-mbedtls 3.0.5-r18`, `apk-transaction-guard 1-r1`, `linux-image-7.3.4-61-openwrt` |
| Driver | `python3 scripts/tests/test-apk-transaction-vm.py --image … --work-dir vm-5` |
| Receipt | `vm-5/validation.json`, `vm-5.log`, `vm-5/vm/serial.log` |

The driver boots the image through `scripts/tests/kernel-upgrade/vm-console.py`
(qcow2 over the raw image, UEFI, isolated user networking). The build's signed
feeds are served from a read-only ext4 NVMe disk, because this kernel has
`CONFIG_NET_9P_VIRTIO` unset and the harness's 9p share cannot mount.

| Check | Result |
| --- | --- |
| Image carries apk r18, the `00-transaction-scope` hook and an enabled `apk-resume.service` | Pass |
| apk started inside a `KillMode=mixed` service (`fake-rpcd`, standing in for rpcd) is moved to `apk-transaction-<pid>.scope` | Pass |
| Shutdown block inhibitor "Package transaction in progress" is listed | Pass |
| `systemctl reboot` during the commit | Refused: `Operation inhibited by "apk" … "Package transaction in progress"` |
| `systemctl stop fake-rpcd` during the commit | apk survived and completed (`OK:`); no journal left |
| Power cut: `apk add --force-reinstall` of 81 packages (the 80 largest non-core packages plus rpcd), QMP `system_reset` after 28 had started | Journal present with 81 changes, `payloads 1` |
| Next boot: `apk-resume.service` | `Result=success`; all 81 changes completed **offline from the journal** in 32 s (feeds disk not mounted) |
| Ordering | resume exited at 50.636756 s; `openwrt-services.service` started at 50.640922 s |
| `apk-resume --status` / journal directory | Nothing pending; `/lib/apk/db/transaction` absent |
| `apk audit --system --packages` | No package of the transaction newly reported |
| `apk fix --simulate` | Nothing to repair |
| `systemctl is-system-running` | `running` |

Runs `vm-1` to `vm-4` are kept for completeness:

- `vm-1` and `vm-2`: the 9p mount failed.
- `vm-3`: an untracked launch, stopped by hand.
- `vm-4`: same product behavior as `vm-5`, but three checks were wrong:
  - the inhibitor table was truncated on the 80-column console;
  - it read a oneshot unit's `ActiveEnter` timestamp, which is 0;
  - it took the exit status of a trailing `ls`.

## Not covered

| Item | Status |
| --- | --- |
| A real version upgrade (old → new identities) cut in the VM | Not performed; the VM transaction reinstalls the image's own versions. Old → new resume is covered by the host test. |
| Kernel package in the VM power-cut transaction, GRUB entry after resume | Not performed in the VM; the database-phase `kernelctl apk-post` replay is covered by the host test |
| Upgrade through LuCI's real rpcd | Approximated by a `KillMode=mixed` service; rpcd itself was not restarted |
| Cut during a C library or systemd write; procd-mode rc script; `/rom` loader fallback in `apk-resume` | Not performed |
| Journal without payload copies (low space, no cache) resuming from the network | Not exercised |
| Physical router: an actual interruption | Not performed (installed and checked only; see below) |

## Publication and router install

Published on 2026-11-12 with `./scripts/publish-changed-feeds.sh`. The dry run
and the real run both passed the full router preflight (receipt
`/srv/openwrt-feeds/upgrade-receipts/1794469353536621886.json`). The
publication also carries kernel generation 61. A full upgrade would change 260
packages: `apk-mbedtls`, `base-files`, the generation-61 kernel, its headers
and kmods.

On the router (`router-admin@192.0.2.1`, running `7.3.4-60-openwrt`), only this
feature was installed. The transaction ran in a transient unit, so an SSH drop
could not cut it off:

```sh
sudo systemd-run --unit=apk-install-transaction-guard --wait --pipe --collect \
	apk add -u apk-transaction-guard apk-mbedtls base-files
```

| Check | Result |
| --- | --- |
| Simulation | Exactly 3 changes: `apk-mbedtls` r17 → r18, `apk-transaction-guard` 1-r1 new, `base-files` 1757.11 → 1758.12 |
| Install | `OK`, exit 0 (log `router-install.log`); `base-files` rewrote its usual `.apk-new` copies of locally modified conffiles |
| Installed | `apk-mbedtls-3.0.5-r18`, `apk-transaction-guard-1-r1`, `base-files-1758.12~ada52cc7ed` |
| `apk-resume.service` / hook | `enabled`; `00-transaction-scope` present |
| `apk-resume --status` | "No interrupted APK transaction.", exit 0 |
| First live commit under r18 (`apk fix apk-transaction-guard`) | Ran in `apk-transaction-19818.scope`, completed `OK`, left no journal |
| `systemctl --failed` | Empty |

Kernel generation 61 was not installed; it arrives with the next ordinary
`apk upgrade` and a deliberate reboot. Logs: `router-install.log`,
`router-verify.log`, `publish.log`, `publish-dry-run.log`.
