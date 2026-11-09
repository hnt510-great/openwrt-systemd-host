# Scheduled OpenWrt integration and publication

Automatic maintenance was disabled at the user's request on 2026-10-18. The
marked cron job was removed, and no scheduler was running. Do not reinstall the
cron job or start this workflow unless the user explicitly requests it again.
Existing logs, state and backups are retained. The description below documents
the previous schedule and the available implementation.

The former host-user cron checked the schedule daily at **04:00 Asia/Singapore (UTC+8)**
with `0 4 * * *`. The host timezone is Asia/Singapore. Actual runs are anchored
exactly 72 hours apart, across month boundaries, with a nonblocking lock preventing
overlap. A newly initialized schedule starts three days after the next configured
04:00 slot. A missed slot runs at the next daily 04:00 check; failed attempts are
recorded and retried at the next scheduled slot. Manual runs preserve the cadence.
The cron entry uses lower CPU and disk I/O priorities for background builds.

Configuration: `configs/scheduled-maintenance.json`. `enabled` defaults to false;
`--scheduled` exits without creating state while disabled. Initialization never
enables scheduling. `--status` does not create or chmod directories.
`timezone` and `start_hour` control initialization; keep the host cron time in
sync with them. Existing schedule state is retained by `--initialize`; changing
an existing anchor requires updating its `next_run` under the scheduler lock.
State, private input backups and per-run logs: `/srv/openwrt-automation`.
Active workspace: `/srv/openwrt-validation/openwrt`. Main-tree and feed merges,
automatic source repairs and image builds all run directly here, reusing its
existing download cache, staging directories and build outputs. No second
checkout is created or maintained. The HDD holds only backups, logs and disposable
VM test disks. Free space is checked on both filesystems before a run.

## What a run does

1. Audit the main repository, nested Git packages and configured Git feeds.
   Stop if a repository already has an unfinished merge/rebase or index lock.
   Snapshot local inputs with temporary indexes and private
   `refs/automation/scheduled-input` references without staging or committing them
   on the user's branches. Include tracked edits and untracked source files;
   exclude and record Python caches, macOS metadata and named backup archives.
   Fail on other untracked files over 16 MiB rather than silently omitting them.
   Save original indexes, patches, stash lists, `.config` and overlays privately.
2. Connect to the user's existing Codex app-server daemon over its private Unix
   WebSocket. Omit model, reasoning and service-tier overrides, inheriting the
   configured default model. Run unattended with writable access to this workspace,
   its Git directories and the per-run backup directory, with network access for
   fetches. Codex merges upstream into the current main/feed branches IN PLACE,
   automatically resolving conflicts while preserving local features. Backup
   snapshots are never merged into the branches. Uncommitted local work remains
   uncommitted; staged changes retain their staging where possible. When edits
   block a merge, Codex temporarily stashes explicit colliding paths and reapplies
   them with `--index`, resolving conflicts and reporting any staging changes.
   Existing user stashes and untracked files must be preserved. Only integration
   resolutions and necessary build repairs are committed. The runner checks exact
   upstream revisions, original HEAD ancestry, branch/stash preservation, no new
   unfinished tracked fixes, and completed merges. Failed integration stops the run.
3. After Git integration, Codex invokes the registered custom-package updater
   once (including Argon's upstream merge and release handling), then the mainline
   kernel updater once. A dirty updater-owned file, update failure or required
   kernel-series port stops integration. Only updater-owned changes are committed,
   separately per repository. Regenerate feed indexes and package links; normalize Kconfig and require
   `conf --fatalrecursive`. Check that all originally selected packages retain their y/m selections, alongside
   native init, libc, APK, signatures and virtualization capabilities. Build
   the complete image with eight jobs by default. The existing publication helper
   reserves the correct kernel generation and timestamp, using its new
   `build-only` mode. Up to two Codex repair attempts can address build failures;
   they cannot silently disable core features. Build commands have time limits,
   and timeout cleanup terminates only the runner's own process groups.
4. Boot the exact compressed image under KVM/UEFI using disposable disks. Boot a
   second copy as a separate LAN client on a private QEMU socket network. The
   router's restricted virtual WAN exposes only a private per-connection test HTTP
   responder through an explicit guest forwarding rule. Check native systemd, procd services,
   WAN DHCP, LAN DHCP/default route, DNS, routed/NATed client HTTP, LuCI HTML,
   authenticated LuCI web login/RPC/UCI, and system board metadata. Provision
   networking, disable external proxy/DDNS integrations and set a temporary root
   password only inside the guests; keep the image and source overlays intact. Always
   stop these test processes and remove their disposable disks. Keep serial
   logs, command logs and a receipt containing the exact image SHA-256.
5. The build helper captures independent image/APK copies and a hash manifest
   under the build lock. VM checks use that saved image; the receipt also identifies
   its artifact manifest. Require every check and unchanged artifact hashes before
   calling the existing signed publisher with the saved package projection. Publish userspace feeds and the complete kernel generation
   to the configured LAN feed server, retaining its existing ABI/signature checks
   and snapshots. An unsuccessful merge, build or VM test cannot reach this step.

This schedule publishes feeds. It does not push Git repositories, install packages
on the physical router, flash firmware or reboot the router. VM checks cover
virtual Ethernet, DHCP/DNS, routing/NAT and LuCI; they do not prove physical NIC,
PPPoE, Wi-Fi or hardware acceleration compatibility.

`/etc/os-release` in a newly built image describes that image. Existing router
identity files remain independent of this host-side scheduler.

## Operations

```sh
python3 scripts/scheduled-maintenance.py --status
python3 scripts/scheduled-maintenance.py --run-now
python3 scripts/scheduled-maintenance.py --resume /path/to/state_root/runs/RUN
crontab -l
```

Do not edit this workspace or run another build/feed update while scheduled
maintenance is running. The lock prevents two scheduled runs; it does not lock out
your editor or manually started build commands. `.config` can be normalized and
the kernel publication sequence advanced by the normal build workflow.

The status JSON includes the next epoch timestamp, last run directory, outcome,
and last successful publication time. Each run records source/snapshot/merge
commit IDs, prompts, daemon JSONL, build logs, VM validation and publication
results. Input backups can contain private overlays; the state root is mode 0700.
Updates and automatic build fixes remain visible in your current workspace.
A failed merge is left intact with backups; resolve the unfinished Git operation
before the next run. There is no automatic reset or rollback of your workspace.

Disable or remove the marked `openwrt-scheduled-maintenance` block with
`crontab -e` to stop future runs. Existing logs and private snapshots
are retained. The previous separate checkout was retired into a one-time private
archive; it is not used for future runs. The schedule needs the host running, cron active, working Codex
authentication/quota, KVM access, upstream access and sufficient disk space.

To test an existing image independently, without publication:

```sh
python3 scripts/test-image-network.py \
  --image bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz \
  --work-dir /path/to/a/new/private-test-directory
```

## Saved artifacts and efficient retries

A completed build stores `artifacts/` privately in its run directory. It contains
independent copies of the tested image, userspace/kernel APK projection, normalized
configuration and kernel input record, plus a SHA-256 manifest. Signing keys are
never copied. The publisher verifies the bundle and copies its APKs into private
publication staging; ordinary signature, retained ELF, router baseline, solver,
immutable identity and promotion checks all remain mandatory.

A publication failure can be retried with `--resume RUN_DIRECTORY`, without
rebuilding or repeating VM checks. Resume accepts only a saved run below the
configured state root with a complete passing receipt bound to its manifest.
When enabled in the future, daily scheduled retries select such runs automatically;
failed VM checks take the full workflow instead. Manual runs preserve the regular
anchor. Failures get a separate retry timestamp at the next configured daily slot.

Every integration still uses Codex and inherits its defaults. After integration
and metadata refresh, a conservative content fingerprint includes repository heads,
tracked/untracked source, overlays, configuration and the existing kernel/tool
fingerprint. Matching the last successful publication, unchanged active feed
manifests and an intact saved artifact bundle permit skipping build/VM/publication.
Unknown or changed inputs take the full path. `phases.json` records progress and
timings; status exposes the last run's phases. Saved artifacts and recovery backups
are retained; insufficient space stops a new run rather than deleting history.

Normalization, build and artifact capture share the checkout build lock, inherited
by the build worker. Integration and metadata refresh still require exclusive user
use of the workspace: editors, raw Git/make and external feed tools do not honor
that lock. There is no automatic workspace reset or cleanup.
