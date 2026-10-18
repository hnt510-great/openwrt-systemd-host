# Updating base-files

Use the signed native-systemd/glibc package from the matching LAN feed. Back up
`/etc` and `/usr/lib/apk/db` before updating; keep the backup private because it
contains account credentials and keys.

```sh
sudo apk update
sudo apk upgrade --simulate base-files
# Review the transaction before running:
sudo apk upgrade base-files
```

Direct installation of an APK file can leave a `base-files><...` checksum
constraint in `/etc/apk/world`, preventing later versions from being selected.
If the simulation skips an available update, inspect `grep '^base-files'
/etc/apk/world`. A reviewed `sudo apk add --simulate --upgrade base-files`, then
`sudo apk add --upgrade base-files`, replaces that constraint with the package
name while upgrading. Do not remove unrelated kernel protection constraints.

## Read-only firmware mount

APK builds retain the `/rom` mountpoint but omit the informational `rom/note`
placeholder. On a running SquashFS system, `/rom` is read-only; attempting to
extract that placeholder made earlier package installs fail and left
`base-files` marked broken. The corrected package uses a higher version so a
normal targeted upgrade selects it. No writable `/rom` workaround is needed.

This is a packaging correction. It does not replace the firmware mounted at
`/rom` or update the running kernel. Changes to boot, init, or filesystem layout
still require validation of the complete firmware and its recovery path.

## Protected configuration

An `.apk-new` file is a proposed package default alongside a locally modified
file. Review and merge these individually; do not replace all of them at once.

- Keep local users, service accounts, groups, and password hashes in `passwd`,
  `group`, and `shadow`.
- Preserve extra entries in `shells` and local tuning in `sysctl.conf`.
- Review `banner` and `openwrt_release` before accepting updated metadata.
- Inspect scripts under `uci-defaults/` before running them on an existing
  router; first-boot defaults can change live configuration.

Archive superseded candidates in the private backup after review. A successful
transaction reports `OK`; `.apk-new` messages alone are not installation errors.

## Sysctl output during upgrades

The post-upgrade hook reapplies sysctl configuration. The init script redirects
normal output to `/dev/null`, keeping stdout open and leaving stderr visible.
Closing stdout with `>&-` caused procps `sysctl` to report
`write error: Bad file descriptor`, even though the APK transaction completed.
The `.2` packaging revision includes this correction. Read-only queries on the
router reproduced the old warning and verified the corrected script returned
success without it.

## Packaging validation

The 2026-10-16 correction was built with
`make package/base-files/compile -j4 V=s`. Tests used the old and corrected signed
APKs in disposable roots inside a private mount namespace, with `/rom` bound
read-only. The old package reproduced the extraction failure both with and
without an existing marker. Upgrading to the corrected package and reinstalling
it both passed, cleared the broken-file flag, and preserved local account,
shell, sysctl, and network files. Signatures, version ordering, and the retained
mountpoint were checked. Package scripts and commit hooks were disabled in these
fixtures; no full-image boot or physical-router upgrade was part of this test.

The subsequent `1730.1` to `1730.2` update was installed on the physical router
using normal `apk upgrade base-files`, with package scripts and commit hooks
enabled. Its post-upgrade hook completed without the stdout warnings. All 54
tracked account, shell, sysctl, SSH, sudo, and router-configuration paths stayed
unchanged; the installed kernel and boot ID also stayed unchanged. SSH/sudo,
procd/ubus service units, and LuCI HTTPS were checked afterward. This was a
userspace package upgrade, not a new firmware boot validation.
