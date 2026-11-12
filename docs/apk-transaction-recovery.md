# Interrupted APK transactions

APK changes packages in two stages. It unpacks every package first, and only
then writes its database (`/lib/apk/db/installed`, `scripts.tar.gz`,
`triggers` and `/etc/apk/world`), runs the post-commit hooks and the kernel
policy (`kernelctl apk-post`). Stock apk-tools 3.0.5 gives up halfway when
interrupted:

- Ctrl-C closes the database without writing it and exits; SIGTERM and an SSH
  hangup kill APK outright, and maintainer scripts receive the same signals.
- After power loss, a crash or SIGKILL, the files of finished packages are new
  while the database still lists the old versions. Triggers, post-commit hooks
  and the kernel's boot entry never ran.
- The verified payloads live in the APK cache, which is tmpfs on this image
  (`/etc/apk/cache -> /var/cache/apk -> /tmp/cache/apk`), so a reboot loses
  them.
- LuCI's package manager runs APK under rpcd, inside
  `openwrt-rpcd@instance1.service` (`KillMode=mixed`). An upgrade that restarts
  rpcd therefore killed its own APK.

The system was never unrecoverable (the GRUB failsafe entry boots the read-only
image without the overlay), but it was left half-upgraded until someone noticed.
This fork now finishes such a transaction automatically.

Validation: [apk-transaction-recovery-validation.md](apk-transaction-recovery-validation.md).

## What changed

| Layer | Component | Behavior |
| --- | --- | --- |
| Commit guard | `0107-openwrt-guard-commit.patch` (apk r18) | From the kernel pre-check to the kernel post-check, SIGINT, SIGTERM, SIGHUP and SIGQUIT are deferred: APK finishes, writes its database and then exits with 128+signal. Maintainer scripts run in their own session (`setsid`). On a live root, `syncfs` runs before and after the database write, so the database never claims files that are not yet on disk. |
| Journal | `0108-openwrt-transaction-journal.patch` (apk r18) | Before the first package write on a live root, APK writes `/lib/apk/db/transaction/journal` (fsynced, atomic rename), copies of the signed indexes it used and of every verified payload (hard links where possible). The directory is removed after the database, post-commit hooks and kernel policy have finished. |
| Refusal | same | While a journal is pending, every other committing APK run is refused with a pointer to `apk-resume`. Simulations still work. |
| Resume | `apk fix --openwrt-resume` | Re-solves the journaled transaction with solver-local identity pins, requires exactly the journaled changes and commits them. If the database had already been written, only the post-commit hooks and `kernelctl apk-post` run again. |
| Boot recovery | `apk-transaction-guard` | `apk-resume.service` runs before `openwrt-services.service` (after ubusd/procd, so maintainer scripts work). `/etc/init.d/apk-resume` (`START=11`) covers procd and recovery boots. |
| Caller isolation | `apk-transaction-guard` hook `00-transaction-scope` | Under systemd, the pre-commit hook moves APK into `apk-transaction-<pid>.scope` and starts `apk-transaction-inhibit-<pid>.service`, a `shutdown:sleep` block inhibitor that lasts until APK exits. |
| Publication | `scripts/apk-upgrade-preflight.py` | The router baseline refuses publication while a journal is pending. |

## Journal

`/lib/apk/db/transaction/` is root-only (mode 0700):

| Path | Content |
| --- | --- |
| `journal` | Text, one record per line: `schema 1`, `boot-id`, `pid`, `started`, `attempt`, `payloads 0/1`, `before-world` and `before-installed` (SHA-256), `world <dep>` for the target world, `repo <n> <index file> <tags>` and `change <old> <old-version> <new> <new-version> <reinstall> <identity>` |
| `phase-database` | Present once APK has started writing its database |
| `repo/<n>/` | Copy of repository *n*'s signed index and the payloads it names |

Payload copies cost up to the transaction's download size on the overlay for
as long as the transaction runs. If the overlay lacks room (download size plus
64 MiB), or a payload is not available locally (no APK cache and a remote
repository), the journal is written without copies, APK warns, and resume uses
the configured repositories and network instead. A transaction that installs
a local `.apk` file by path is journaled without copies.

## Operating it

```sh
apk-resume --status     # exit 0: nothing pending; exit 1: a journal is pending
sudo apk-resume         # finish it now (exit 0 done, 1 failed, 75 APK busy)
journalctl -u apk-resume.service
```

Normally nothing needs doing: the next boot finishes the transaction before
router services start. If an attempt fails, `/run/motd.d/50-apk-resume`
carries a login notice until a later attempt succeeds.

**Resume decisions.**

1. The installed database still matches the journal's `before-installed`
   hash, so APK never wrote it. The full transaction is solved and committed
   again: every changed package is reinstalled from the journal copies, their
   scripts and triggers run, and the database is written. A package that was
   already unpacked has its maintainer scripts run a second time. OpenWrt's
   `default_postinst` is idempotent; a third-party script that is not may
   need attention.
2. The database differs and `phase-database` exists, so APK had written it.
   The world is rewritten from the journal, then the post-commit hooks and
   `kernelctl apk-post` run, which registers a newly installed kernel in GRUB.
3. The database differs but `phase-database` is missing: something else
   changed it. `apk-resume` refuses and keeps the journal for manual review.

**Do not delete the journal to get APK working again.** That turns a
recoverable state into an untracked mix of old database and new files. If
resume fails, read `journalctl -u apk-resume.service`, fix the cause
(for example, disk space, or network when there are no payload copies) and
run `apk-resume` again. Each attempt increments `attempt`.

**When the normal boot cannot reach the resume step.** If a cut-off upgrade of
the C library or systemd prevents a native boot, `openwrt-systemd-prepare`
falls back to procd, whose `apk-resume` init script runs the same tool. If the
installed `apk` cannot load its libraries, `apk-resume` retries with the
read-only image's loader and APK (`/rom/usr/lib/ld-linux-*.so.*
--library-path /rom/usr/lib /rom/usr/bin/apk`), provided that image already
carries apk r18. As a last resort, boot the GRUB **failsafe** entry, then:

```sh
mount_root
apk-resume
```

**Shutdown blocking.** With the guard installed, a systemd block inhibitor
(`systemd-inhibit --list`) is held while a commit is in progress, so `reboot`
and `systemctl reboot` refuse to proceed. `systemctl reboot
--check-inhibitors=no` overrides it, and the journal then has to repair the
interruption.

## Scope and limits

- Journaling and resume apply to the running system (`--root` absent or `/`).
  Offline image assembly (`--root` elsewhere) is unchanged unless
  `APK_OPENWRT_JOURNAL` is set (host tests only).
- No file-level rollback exists: an interruption is always completed forward.
  Kernel rollback remains `kernelctl` and GRUB's job
  ([kernel-upgrade.md](kernel-upgrade.md)).
- The guard cannot defer SIGKILL, OOM kills or power loss; the journal covers
  those.
- Package scripts that hang still hang; `apk-resume.service` times out after
  30 minutes and leaves the journal.
- Related: [APK upgrade preflight](apk-upgrade-preflight.md),
  [LAN APK feeds](lan-apk-feeds.md).

## Verification

```sh
python3 scripts/tests/test-apk-transaction-journal.py
APK_RESUME_SHELL='busybox ash' python3 scripts/tests/test-apk-transaction-journal.py
KERNEL_POLICY_APK=$PWD/staging_dir/host/bin/apk python3 scripts/tests/test-kernel-apk-policy.py
python3 scripts/tests/test-apk-upgrade-preflight.py
```

The journal test needs passwordless `sudo` and a static C compiler. It builds
signed fixture repositories, interrupts the patched APK at chosen points from
a maintainer script or commit hook, and finishes the transaction with the
packaged `apk-resume` against a disposable `--root`.
