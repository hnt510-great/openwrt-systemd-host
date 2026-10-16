# Scheduled OpenWrt integration and publication

The host user's cron checks the schedule hourly. Actual runs are anchored exactly
72 hours apart, across month boundaries, with a nonblocking lock preventing
overlap. The first run is scheduled three days after the next whole hour when
initialized. A missed slot runs at the next cron check; failed attempts are
recorded and retried at the next scheduled slot. Manual runs preserve the cadence.
The cron entry uses lower CPU and disk I/O priorities for background builds.

Configuration: `configs/scheduled-maintenance.json`.
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
3. Regenerate feed indexes and package links; normalize Kconfig and require
   `conf --fatalrecursive`. Check that selected core capabilities survived. Build
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
5. Require every check and the unchanged image hash before calling the existing
   signed publisher. Publish userspace feeds and the complete kernel generation
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
