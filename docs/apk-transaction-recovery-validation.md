# Interrupted APK transaction validation

Implementation and host validation: 2026-11-12, in this checkout. Evidence is
under `/srv/openwrt-validation/apk-transaction-validation-20261112/` (kept outside
the repository). No image was built, no VM was booted, nothing was published,
and no physical device was flashed or changed. The physical router was only
inspected read-only during design: its overlay layout, its tmpfs APK cache and
rpcd's cgroup and `KillMode`.

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

## Not covered

| Item | Status |
| --- | --- |
| Exact-image VM: power cut (`system_reset`) during a multi-package upgrade, `apk-resume.service` ordering before `openwrt-services.service`, kernel package registered in GRUB after resume | Not performed |
| LuCI upgrade that restarts rpcd surviving in its scope | Not performed (scope move proven on the host's systemd only) |
| `reboot`/`systemctl reboot` refusal while the inhibitor is held | Not performed; inhibitor registration only |
| procd-mode rc script and the `/rom` loader fallback in `apk-resume` | Not performed |
| Journal without payload copies (low space, no cache) resuming from the network | Code path not exercised by the host test |
| Physical router | Not deployed |

These need an image built with apk r18 and `apk-transaction-guard` before a VM
gate. The first live use of the patched APK on a router is also the first
upgrade that the journal can protect; the APK self-upgrade itself runs under
the old binary.
