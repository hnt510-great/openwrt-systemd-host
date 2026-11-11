# Restart advice on native-systemd OpenWrt

Select `openwrt-needrestart` under Utilities and optionally
`luci-app-needrestart` under LuCI applications. These packages target the
x86_64/glibc/APK native-systemd variant. Neither package changes service lifecycle
ownership or restarts workloads.

```
sudo needrestart
sudo needrestart --json
sudo needrestart --cached --json
```

Fresh scans update a root-only, atomic report in
`/run/openwrt-needrestart/report.json`. Exit codes are 0 for complete coverage,
2 for partial/stale coverage, and 1 for a failed request. Findings do not change
a complete scan's exit code. JSON `schema_version: 1` contains `boot_id`,
`timestamp`, `complete`, `scan_status`, `warnings`, process counts, `services`,
`containers`, and `kernel`. Service entries contain lifecycle ownership,
recommended action, disruption advice, and affected PIDs/start times/files.
File entries distinguish `replaced` and `removed`; package metadata describes
the currently installed APK, never an inferred in-memory version.

LuCI's **Status → Restart Needed** page shows the same evidence, kernel status,
container image changes, and scan time. **Scan now** queues inspection; it has no
restart action. A status overview link displays the last report's summary.
The `luci-app-needrestart` read ACL permits only the fixed
`luci.needrestart.status` and `scan` methods. It grants no generic file execution
or lifecycle permissions. Evidence is rendered as text, not HTML.

## Automatic scans and consistency

The live APK post-commit hook queues a request and prints where to find the
report. A systemd path unit starts a short-lived worker; no polling daemon or
periodic timer is added. The worker waits for APK's database lock because this
tree completes kernel activation **after** ordinary post-commit hooks.
It holds a shared database lock during a scan, bounded to 20 seconds, so another
APK transaction cannot replace files midway through inspection. A concurrent
upgrade can wait for that bounded scan. Queue acknowledgement has a separate
short lock and inode check, so a newer request survives an active scan.
Changes to kernel state or queue inputs produce a partial report and retain the
queued request for another scan. A worker can wait up to 60 seconds for APK;
manual scans wait up to 2 seconds. Failures are visible through the journal and
RPC error status and do not change the package transaction's exit code.

Offline image assembly and procd recovery do not queue inspection. Fresh and
cached CLI queries require root and a native-systemd boot. No existing
maintenance service is started or enabled. Removing the package stops only its
own reporting path/worker.

## What the report means

The scanner reads `/proc/PID/exe` and executable file mappings. Deleted code
and verified content replacements identify obsolete binaries or shared objects;
identical readable replacements are suppressed. Anonymous mappings, memfd/JIT
code, and deleted non-executable data are excluded. Overlay inode differences
alone do not establish obsolete code. Inaccessible comparisons produce partial
coverage. Paths resolve inside the process root using `openat2` with
`RESOLVE_IN_ROOT|RESOLVE_NO_MAGICLINKS`, including absolute symlinks. PID start
times are rechecked before publishing process evidence.

OpenWrt slices and current procd instance records identify original init-script
owners, including legacy descendants. Native/user services use libsystemd's
process ownership APIs. Advice never targets an OpenWrt transient scope.
Supervisor infrastructure requires maintenance review; network/SSH/RPC services
are marked potentially disruptive. Unassigned processes remain separate.
The optional systemctl service bridge is not required.

Kernel advice consumes the existing kernel-manager state and verifies the GRUB
one-shot trial selection. `reboot-pending` means a ready, armed, different-ABI
candidate; `trial-running` requires no additional reboot. A same-exact-ABI
generation change never creates a required-reboot warning. Missing metadata,
rejected candidates, or unarmed selections remain unknown/incomplete. The tool
does not arm, confirm, remove, upgrade, or roll back kernels.

Podman stores are discovered from live rootful/rootless container cgroups.
Both `libpod-<id>.scope` and Quadlet's `libpod-payload-<id>` layouts are
recognized, including nested cgroups.
Host-side Podman inspection runs under the owning UID with a clean environment;
it does not initialize stores for arbitrary accounts or start API sockets.
Rootless file comparisons run in bounded children under the owning account,
including FUSE overlays that deny host root. These children discard inherited
host locks/descriptors and cannot acquire new privileges or expose process dumps.
After dropping host credentials they join only the target user namespace for
FUSE access; mount/PID namespaces and container executables are not entered.
Rootless processes can map host files through bind mounts, such as a shared
home directory. Overlayfs reports its superblock device in `maps` but a
per-layer device from `stat`, so those mappings need the old object for a
content comparison, and only host root may open `/proc/<pid>/map_files`. Root
opens that object, and hands it to the unprivileged child, only when every
mount of the mapped device in the process's mount table is a non-FUSE
filesystem; FUSE-backed mappings keep the conservative unverified warning.
Container paths are compared inside their own filesystem. Reports retain only
identity, account, image IDs/reference, and a verified systemd controller when
available; container environments and raw inspection output are discarded.
A configured local tag resolving to a different image ID is `changed`:
**recreation through the deployment controller** is needed to use that image.
Restarting an existing container does not substitute its image. Identity
differences do not prove chronological or security version ordering.
Digest-pinned references remain pinned. There are no registry queries or pulls.
Other runtimes/unverified isolated roots have explicitly incomplete coverage.
Sandboxed `slirp4netns` and `passt`/`pasta` processes (including their AVX2
variants) are inspected as host helpers only when their
executable matches the installed host binary and their owning user unit
controls an inventoried container. Their host code remains checked for stale
libraries; an unverified helper retains incomplete coverage.

Firefox ESR children chrooted into `/proc/<pid>/fdinfo` are inspected through
host paths only after verifying their host mount namespace, live same-user
parent rooted at the host filesystem, and shared executable object. The browser
sandbox stays enabled; findings belong to the owning application/session.
Other private roots and unverified parents retain incomplete coverage.

Native systemd services can chroot after loading their code; `rtkit-daemon`
enters `/proc`. Their mappings are resolved from the root of the service's own
mount namespace, obtained by a short-lived child that joins only that namespace
to return an `O_PATH` descriptor. This applies only to a system `.service` unit
that owns the process's cgroup and shares the host user namespace, and only when
the namespace root is the host root object. Findings then carry ordinary
`systemctl restart` advice. Services with a private `RootDirectory=`/`RootImage=`
or another user namespace retain incomplete coverage.

Flatpak instances are identified by their scoped application ID and instance ID,
owning UID, host instance metadata, sandbox child PID, mount namespace, and root
identity. The scanner reads only app/runtime/extension deployment identity from
`.flatpak-info`; environment values and bus policies are discarded. It compares
running commits with active deployments in the ordinary user/system Flatpak
stores, including extensions installed in multiple branches. No Flatpak command,
network request, update, or application restart is performed during scanning.

Flatpak D-Bus proxies use a separate sandbox. They are associated only after
matching the owning UID, exact application cgroup, selected instance metadata,
live verified application child, and installed host executable contents. Their
host executable mappings are then checked without entering the sandbox.

Podman bridge networks can share a rootless network helper outside any individual
container service. Its owned PID record, user namespace, live inventoried
container identity, tmpfs sandbox, and installed executable contents are verified
before checking host mappings. Per-service network helpers remain supported.

Unknown isolated roots remain partial coverage. Their warnings include PID,
executable, and cgroup so independent gaps no longer collapse into one generic
message. A coverage warning is not by itself evidence of obsolete code or a
failed service; actual restart advice is reported separately.

Changed Flatpak deployments produce `flatpak` relaunch advice in the existing
affected-services table. Evidence type `flatpak-deployment` identifies a ref,
rather than an individual file. CLI output also lists inventoried Flatpaks;
JSON includes an additive `applications` array with per-component status.
Unverified instance identity, nonstandard stores, or unresolved deployments
retain incomplete coverage. A known update still produces advice if another
component is unverified. Local commit identity does not establish registry
freshness or security patch status.

Kernel inventories have a separate 16 MiB input limit. Reports and command
output retain their 4 MiB bounds. ELF comparisons stream through fixed-size
buffers without a file-size cutoff and remain subject to the overall scan
deadline. If a comparison cannot finish in time, coverage remains partial.
Within a scan, a bounded cache reuses completed comparisons only while both
file objects' identity, size, mtime, and ctime match. Metadata is checked again
after reading; changed objects are compared again rather than trusting a stale
result. This avoids rereading shared browser libraries for every child.

This is a snapshot of observable native code and local activation state.
Interpreted scripts/modules, in-place modifications without a retained old
object, microcode, remote image updates, and service health are not assessed.
A clean result within assessed coverage is not a claim that all software is
patched. Cached results retain their timestamp and require a fresh scan after
manual restarts or container-image operations.

## Validation

```
python3 -B scripts/tests/test-needrestart.py
python3 -B scripts/tests/test-luci-needrestart.py
node scripts/tests/test-luci-needrestart.js
make -j2 package/custom/openwrt-needrestart/compile \
  package/custom/luci-app-needrestart/compile \
  CONFIG_PACKAGE_openwrt-needrestart=m CONFIG_PACKAGE_luci-app-needrestart=m V=s
```

The binary fixture override exists only in a separately compiled
`NEEDRESTART_TEST` build. Production binaries contain no root, process, ubus, or
Podman fixture overrides. The Python suite uses the target compiler and glibc
loader and skips explicitly when prerequisites are absent.

Use `python3 scripts/tests/build-needrestart-fixtures.py DIRECTORY` to cross-build
the ELF fixtures. `scripts/tests/needrestart-guest.py --disposable-vm --fixtures DIRECTORY` tests
actual executable/library replacement, native/procd ownership, manually cleared
findings, APK lock ordering, and RPC reporting. Its directory requires a target
`dl-worker` taking a shared-library path plus `libprobe-v1.so` and
`libprobe-v2.so` with different ELF contents. Run it only in a disposable VM;
it creates and removes dedicated fixture services. Package/fixture checks and
guest checks are separate from signed publication or physical deployment.

The [validation record](needrestart-validation.md) identifies the accepted image,
signed APKs, automated checks, live guest results, and remaining validation limits.
