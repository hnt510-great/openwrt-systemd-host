# needrestart validation — 2026-10-21

The feature was built and exercised in isolated disposable QEMU/KVM guests.
The accepted packages were subsequently published and deployed to the physical
router on 2026-10-21; the deployment evidence and coverage limits are below.

## Accepted artifacts

Artifacts and logs:

    /srv/openwrt-validation/openwrt-needrestart-validation-20261021-0apy5pee

Accepted image: `openwrt-x86-64-generic-squashfs-combined-efi.img.gz`

SHA-256:

    6aabcb5106ae38557d942ac69693b7197a4f18e6861bc73a8b9738942b07a80d

| Final signed package | SHA-256 |
| --- | --- |
| openwrt-needrestart-1.0.0-r1.apk | b16767a5a66a26297b41166412c9ae7152461bdaa704e65c955f0dc8be9701cc |
| luci-app-needrestart-1.0.0-r1.apk | 3a3916f1b4650bdc3802fe2231684d6bb8e475e41a1825f0473d9357001ae78d |

The image was booted through a fresh qcow2 overlay with UEFI, KVM, two vCPUs,
2 GiB RAM, and isolated restricted user-mode LAN/WAN networks. The final guest
boot ID was `00000000-0000-4000-8000-000000000004`. Its kernel was
`6.18.55-owrt-d7ef8dc7f60b053d6a57a4f73b5dad2b-r1-g22`, with exact ABI
`6.18.55~d7ef8dc7f60b053d6a57a4f73b5dad2b-r1`.

The installed scanner's SHA-256 matched the stripped image payload:

    2cf1394e74941c6dbabf7a1c156bfbcbfa8ad28745171b598b85404c6ebd3603

## Builds and automated checks

The existing working tree and configuration were retained. The optional
packages were selected using command-line overrides; existing unrelated work
was preserved and can be reflected in the full image.

```
make -j8 V=s CONFIG_PACKAGE_openwrt-needrestart=y \
  CONFIG_PACKAGE_luci-app-needrestart=y \
  BIN_DIR=/tmp/needrestart-validation/images
```

After the final reporting-unit removal adjustment, the core package, package
installation, and target image stages were rebuilt in sequence. The prepared
scanner source matched the repository source byte-for-byte. Its SHA-256 was
`6fa421d070a1335317417968e311bf7f2f42f26a02436aab6603742c017cba06`.

| Check | Result |
| --- | --- |
| Compiled scanner fixture tests | 39 passed |
| Real ucode RPC backend tests | 7 passed |
| LuCI DOM/RPC rendering tests | Passed: loading, queue/running, evidence, escaping, errors, overview |
| C checkpatch | 0 errors, 0 warnings |
| Strict Kconfig validation | Passed using a temporary configuration with both packages selected |
| Both package builds and complete firmware build | Passed |
| User `.config` preservation | Byte-for-byte unchanged |

The scanner tests cover ELF replacement/removal and identical-library
suppression, deleted data/JIT exclusions, procd slices and degraded placement,
multiple instances, native/user services, supervisor advice, unknown ownership,
exiting/reused PIDs, partial coverage, confined absolute symlinks, kernel
activation states, local image identity and separate stores, queue replacement,
state changes during scanning, first-boot APK locking, and absence of fixture
overrides in production binaries.

## Live guest results

| Check | Result |
| --- | --- |
| Fresh final-image report | Complete, no warnings, no affected processes; kernel current |
| Atomic replacement of a running native-service executable | Correct native unit and obsolete file reported |
| Replacement of an actually loaded shared library | Native service and replaced library reported |
| Replacement of a procd-supervised executable | Original init-script owner reported |
| Manual owner-controlled restarts | Corresponding findings cleared on a fresh scan |
| APK hook while transaction lock held | Queued without scanning prematurely; published after lock release |
| Live LuCI ubus methods | Status and asynchronous scan succeeded |
| Rootful and rootless Podman | Both stale container executables detected |
| Local image reference moved to a different ID | Rootful recreation advice; rootless store remained independently current |
| Final APK signature checks | Both accepted by target APK keys |
| Exact final APK simulation and installation | Passed offline; only the two feature packages installed |
| Package removal | Both reporting units inactive; procd/ubusd main PIDs and running kernel unchanged |

Rootless FUSE overlays required a comparison helper that drops host credentials
and joins only the target user namespace. The live rootless replacement test
passed using this path. The helper does not enter mount/PID namespaces, execute
container code, inherit host locks, or enable FUSE access for other users.

Kernel pending-trial, same-ABI-generation, rejected/unarmed candidate, and
incomplete-adoption decisions were tested with fixtures. A live kernel upgrade
was not performed. LuCI JavaScript rendering was tested with DOM/RPC fixtures
and its backend through live ubus; graphical browser inspection was not run.
These results establish package and disposable-VM behavior, not physical-device
deployment or validation.

## Signed publication and physical deployment

Published the two accepted `1.0.0-r1` APKs in snapshot
`20261021T035002.196904Z`, under ABI
`6.18.55~d7ef8dc7f60b053d6a57a4f73b5dad2b-r1`. A source projection containing
only these two artifacts was passed to the incremental userspace publisher
with `--kernel-upgrade-view`. Both `base` and its `custom` projection gained
the packages; all pre-existing APK hashes and kernel artifacts were preserved.
The dry-run, publication result, and previous manifest are in the artifact
directory above.

Installed on `OpenWrt` at `192.0.2.1` using its existing SSH account and sudo.
The router downloaded the published APKs, verified their signatures with its
configured keys, and matched both accepted SHA-256 hashes. Offline simulation
and installation added exactly the two feature packages, with no removals or
upgrades. A ten-minute automatic uninstall rollback timer was armed before
installation and canceled after the health checks passed. The configuration
backup remains under `/root/needrestart-deploy-20261021` on the router.

The APK hook queued the first report, the path unit remained active, and the
worker completed successfully. `luci.needrestart.status` and `scan` worked,
and the installed scanner matched the accepted stripped-binary hash. LuCI's
root URL returned HTTP 200 and its login page rendered at the authenticated
entry point (HTTP 403 without a session); authenticated visual testing was
not performed. Existing `luci.getFeatures`, LAN status, and local DNS worked.

Boot ID `00000000-0000-4000-8000-000000000005` and running kernel
`6.18.55-owrt-d7ef8dc7f60b053d6a57a4f73b5dad2b-r1-g21` stayed unchanged.
Configuration/key hashes, rc.d links, and checked procd/ubusd/DNS/web/RPC and
container-helper PIDs were unchanged. Three existing rootless Podman containers
remained running. Scheduled maintenance stayed inactive. No workload restart,
kernel upgrade, or reboot was performed.

The initial `r1` physical report was **partial**, not a clean-bill-of-health result. It found
removed `libattr.so.1.1.2502` and `libacl.so.1.1.2302` mappings in
`systemd-journald.service`, `virtqemud.service`, and `virtstoraged.service`.
These services were left running. Some isolated/rootless mappings could not
be verified or attributed to a container owner. Kernel state was unassessed:
the physical manager's state file is 4,812,118 bytes, above the scanner's 4 MiB
JSON input bound. This does not indicate a reboot requirement.

`physical-deployment-evidence.tar.gz` contains the target transaction logs,
report/RPC evidence, and before/after state checks;
`rootless-containers-after.log` records the existing running containers.

## Remote scan corrections: r2 and r3

The physical warnings were investigated without changing workload configuration
or restarting services. The final installed scanner is `1.0.0-r3`; the LuCI
package remains `1.0.0-r1` with the same report/RPC schema.

Corrections:

- Recognize Quadlet `libpod-payload-<64 hex ID>` cgroups, retaining strict ID
  and component boundaries. This enables rootless inspection and inventory.
- Read kernel inventories through a separate 16 MiB bound. The physical
  inventory exceeds the former shared 4 MiB bound.
- Retry interrupted rootless-helper polling/receive calls within the original
  absolute timeout. A SIGCHLD from an earlier probe must not terminate a healthy
  probe and produce a false permission denial. Preserve the actual open error
  when also checking an old file's ELF header.
- Compare ELF files up to 256 MiB using fixed-size buffers and the existing
  deadline. The physical Python executable is 115,747,328 bytes, above the old
  64 MiB comparison bound.
- Inspect sandboxed `slirp4netns` as host helpers only after matching the
  installed executable's content, owning UID, tmpfs sandbox, and an inventoried
  container's user-service controller. Unknown roots and unmatched binaries
  retain partial coverage. Stale helper libraries still produce service advice.

Validation: 50 compiled scanner tests, 7 real ucode tests, LuCI rendering tests,
and C checkpatch passed. The signed `r3` APK was installed in a disposable clone
of the accepted, adopted UEFI/KVM guest. Live tests covered identical replacement
of a 112 MiB executable, a kernel inventory over 4 MiB, native/procd executable
and library changes, APK locking and queue acknowledgement, and LuCI RPC.
Rootful, rootless, and rootless split-cgroup containers were checked; the split
case used a real sandboxed slirp4netns helper. Repeated untraced scans had no
warnings. Stale container code and changed local images remained detectable.
The final VM scan was complete, with no warnings and kernel current.

The first fresh guest lacked completed kernel-manager adoption and rejected
the APK transaction. Runtime upgrade testing therefore used a disposable
overlay of the previously validated, adopted guest; no router kernel-manager
changes were used to work around that VM prerequisite.

Published `r2`, then the further `r3` corrections, as new immutable filenames.
The final snapshot is `20261021T041018.967256Z`; only the core package and its
custom-feed projection were added at each step. All previous APK hashes and
kernel artifacts were preserved.

| Final artifact | SHA-256 |
| --- | --- |
| openwrt-needrestart-1.0.0-r3.apk | a257d8d939abdaa44a8089625cb6e8b641da518d2e1619fb8fcdb0f549a7fa68 |
| Installed stripped scanner | d1c03ee5e545105d04916057f1b38caea05cd1c007f1ce8e44b75412aeb7ef4e |

On the physical router, signatures/hashes and exact offline simulations passed.
Each transaction upgraded only `openwrt-needrestart`; no other package changed.
Signed previous packages and timed rollback were prepared, and rollback timers
were canceled only after preservation/health checks passed.

Three fresh final CLI scans and a LuCI-queued worker scan all returned
`complete=true`, zero warnings, zero unreadable processes, kernel `current`,
and the same three running rootless containers with local image status
`current`. The existing restart advice for journald, virtqemud, and virtstoraged
remains visible; none was restarted. This is local image identity, not a
registry freshness or security-version check.

Boot ID, running kernel, kernel-manager state hash, configuration/key hashes,
and checked procd/ubus/DNS/web/RPC/container-helper PIDs were unchanged.
Scheduled maintenance remained inactive. No kernel upgrade, reboot, or workload
restart occurred. DNS and LuCI RPC health checks passed.

Evidence, both signed updates, publication receipts, and final reports are in:

    /srv/openwrt-validation/openwrt-needrestart-r2-validation-20261021-3d92yyfv

The remote deployment/rollback directory is
`/root/needrestart-fix-20261021`. The final CLI/RPC evidence is also archived
locally as `physical-deployment-evidence.tar.gz`.

## Pasta network-helper correction: r4

After the router switched to native container storage and pasta networking,
`r3` again reported an isolated-filesystem coverage warning. All three affected
processes were pasta helpers whose executable resolved to `/usr/bin/passt`,
inside tmpfs sandboxes under their container user units' `/runtime` cgroups.
They were not unknown container payloads.

`1.0.0-r4` extends the existing host-helper allowlist to `passt`, `pasta`, and
their `.avx2` variants. The executable-content, owning UID, tmpfs sandbox, and
inventoried user-service controller checks remain mandatory. Lookalike paths,
unmatched binaries, and helpers without a verified controller retain partial
coverage. No Podman/network/storage configuration was changed for this fix.

Validation passed: 57 scanner tests, 7 real ucode tests, LuCI rendering tests,
package compilation, and C checkpatch with zero errors/warnings. A disposable
UEFI/KVM clone of the accepted adopted guest received the signed `r4` APK and
the existing signed passt APK. The older guest required a test-user-specific
TUN ACL before pasta could start; that prerequisite adjustment was confined
to the disposable VM. The first attempt's log records this permission failure.

The final live test exercised a real pasta-backed split-cgroup container and
repeated scans without warnings, plus rootful/rootless image and executable
replacement, a 112 MiB ELF, a kernel inventory over 4 MiB, APK hook locking,
and LuCI scan/status. The final guest report was complete with kernel current.

Only the signed needrestart update was published, with its custom-feed
projection, in snapshot `20261021T091544.680403Z`. All existing published APK
hashes and kernel artifacts were preserved.

| Final artifact | SHA-256 |
| --- | --- |
| openwrt-needrestart-1.0.0-r4.apk | 3a1d32900fb3369cc90f53a7de8d2001a252cc1e19a6f8309a7e090b5dd6464b |
| Installed stripped scanner | 2ac5ba0f18f5f32854ff0f33d342ac5c364c3ed9a1555f480ad946db61c7af08 |

The router verified the signature and exact hash, simulated the offline
transaction, then upgraded only needrestart from `r3` to `r4`. A signed `r3`
rollback package and timed rollback were prepared. Three fresh scans and a
LuCI-queued scan returned complete coverage, zero warnings, three containers
with matching local images, and kernel current. The rollback timer was canceled
after preservation and DNS/LuCI checks passed.

Boot ID, running kernel, kernel-manager state hash, configuration/key hashes,
checked procd/ubus/DNS/web/RPC/network-helper PIDs, and running container IDs
were unchanged. Scheduled maintenance stayed inactive. The three existing
service restart recommendations remain; no workloads were restarted or rebooted.

Evidence and signed package:

    /srv/openwrt-validation/openwrt-needrestart-r4-validation-20261021-bu5gpexf

Remote transaction/rollback directory: `/root/needrestart-r4-20261021`.

## Large executable comparison correction: r5

The next physical partial-coverage warning came from three running Codex
processes. Their native executables were each 296,865,480 bytes, above the
256 MiB comparison limit. The container and kernel checks were already working.

`1.0.0-r5` removes the file-size cutoff instead of raising it again. ELF
comparison streams through two fixed 64 KiB buffers and checks the existing
scan deadline before each chunk. An unfinished/unreadable comparison still
produces partial coverage. Final short chunks advance by their actual size.
Neither the report/input bounds nor the rootless probe timeout were relaxed.

Validation passed: 58 scanner regression tests, 7 real ucode tests, LuCI
rendering tests, package compilation, and zero-error/zero-warning checkpatch.
The new regression checks identical 300 MiB ELF mappings and a difference at
offset 290 MiB. A disposable UEFI/KVM clone also verified identical replacement
of a running 300 MiB executable and detection of a subsequent late-file change.
The complete native/procd, kernel inventory, rootful/rootless container, real
pasta helper, local-image, APK hook, and LuCI RPC tests passed. The old guest's
test-user TUN ACL was prepared only inside the disposable VM.

The signed APK was published in snapshot `20261021T093700.184821Z`. Only
needrestart and its custom-feed projection were added; pre-existing APK hashes
and kernel artifacts were preserved.

| Final artifact | SHA-256 |
| --- | --- |
| openwrt-needrestart-1.0.0-r5.apk | 87b120a3c6b00a8bde90dea7e0ba2227957e87ea64a2e9d4f7f1f4676c4fdc2b |
| Installed stripped scanner | 6da07de502f5f0da02c054314deb8bebeac3ea437a2ec0c93687baa531ed2ccc |

Target signature/hash verification and offline simulation passed; only
needrestart upgraded from `r4` to `r5`. A signed `r4` rollback APK and ten-minute
rollback timer were prepared. Three fresh physical scans were complete with
zero warnings, taking 1.32, 1.37, and 1.34 seconds. A LuCI-queued scan also
completed without errors. Kernel status was current, all three container local
images matched, and the three existing service restart recommendations remained.

Boot ID, running kernel, kernel-manager state hash, configuration/key hashes,
and checked service/network-helper/Codex PIDs were unchanged. Container IDs
were preserved, DNS/LuCI checks passed, and scheduled maintenance stayed
inactive. The rollback timer was canceled after validation. No workload was
restarted and no reboot occurred.

Evidence, signed package, and publication receipts:

    /srv/openwrt-validation/openwrt-needrestart-r5-validation-20261021-6k41kx8n

Remote transaction/rollback directory: `/root/needrestart-r5-20261021`.

## Firefox sandbox correction: r6

The next remote report showed `No such process` errors for live Firefox child
processes plus an unknown-isolated-filesystem warning. These children were
chrooted into `/proc/<sandbox-helper-pid>/fdinfo`, whose associated task had
gone away. Their own PIDs were alive; the scanner was resolving code against
the intentionally unusable sandbox root.

`1.0.0-r6` permits host-path inspection only for the known Firefox ESR executable
and exact proc-fdinfo chroot form, after checking the host mount namespace,
same-user live parent, parent host root, and identical child/parent executable
object. Parent start time is rechecked. Replaced browser executables can still
be detected. Unknown roots, private mount namespaces, and mismatched parents
remain partial. No browser sandbox settings are weakened, namespaces entered,
or inspected executables run by the scanner.

A 512-entry per-scan cache avoids repeated full comparisons of libraries shared
by browser children. Cache keys include both objects' device/inode, size,
mtime, and ctime. Completed reads revalidate metadata; unresolved comparisons
are not cached. Fixed buffers and the original scan deadline remain in effect.

Validation passed: 65 scanner tests, 7 real ucode tests, LuCI rendering tests,
package compilation, and zero-error/zero-warning checkpatch. Added tests cover
realistic browser proc roots, stale libraries and replaced executables, rejected
parent/namespace/root cases, and mutation of a cached file between process scans.

The signed APK was installed in a disposable adopted UEFI/KVM guest. Its full
live suite passed, including large ELF changes, kernel inventory, native/procd
ownership, rootful/rootless containers, pasta, APK queues, and LuCI RPC. The new
browser test launched Firefox as an ordinary test user with a temporary profile,
required real proc-fdinfo sandbox children, and verified three complete scans
without disabling sandboxing. Test containers and browser were stopped only
inside the disposable guest.

Published snapshot: `20261021T151914.614412Z`. Only needrestart and its custom-feed
projection were added; all existing APK hashes and kernel artifacts were retained.

| Final artifact | SHA-256 |
| --- | --- |
| openwrt-needrestart-1.0.0-r6.apk | aed9bac557093223b0cfa7f0630aec037910120228c0d4842d268acc8fdb6646 |
| Installed stripped scanner | e30794c617d09e9b38dbadfd00d7e75b2995456483a3044def1bebe9ea380105 |

Remote signature/hash verification and exact offline simulation passed; only
needrestart upgraded from `r5` to `r6`. A signed prior package and ten-minute
rollback timer were prepared. Three fresh CLI scans completed with zero warnings
and no restart recommendations in 0.86, 0.83, and 1.03 seconds. LuCI's queued scan
also passed: 123 processes, zero unreadable processes, four inventoried containers
with matching local images, and kernel current.

Boot ID, running kernel, kernel-manager state, configuration/key hashes, checked
service/network-helper/Firefox/Codex PIDs, and container IDs were preserved.
DNS/LuCI health checks passed; scheduled maintenance remained inactive. The
rollback timer was canceled. No remote workload was restarted or rebooted, and
the user's Firefox session and sandbox remained intact.

Evidence, signed package, and publication receipts:

    /srv/openwrt-validation/openwrt-needrestart-r6-validation-20261021-7moxlnj0

Remote transaction/rollback directory: `/root/needrestart-r6-20261021`.

## Flatpak instance correction: r7 — 2026-10-22

The next isolated-filesystem warning came from the Flatpak-packaged Fcitx5
input method (`org.fcitx.Fcitx5`), including its bubblewrap process. `r6` had no
Flatpak identity or deployment assessment and correctly left that root unknown.

`1.0.0-r7` verifies the owning UID, app/instance scope, selected sandbox and host
instance metadata, live sandbox child, mount namespace, and filesystem root.
App, runtime, and extension commits are compared against active local user or
system deployments. Extension branches are checked separately, including the
multiple GL.default branches used by the actual runtime. Missing/ambiguous
metadata stays partial; no generic isolated-root warning is simply suppressed.
Environment values and bus policy are not retained in reports. A verified
bubblewrap executable is inspected against its host files; the application code
remains inspected inside its sandbox root.

An additive `applications` inventory records component status. Changed local
deployments produce a Flatpak relaunch recommendation through the existing
services/evidence interface, including when native code inside an immutable old
deployment has not changed. The LuCI package remains `1.0.0-r1`; no frontend or
application package was modified or deployed.

Validation passed: 76 compiled scanner tests, 7 real ucode tests, LuCI rendering
tests, package compilation, and zero-error/zero-warning C checkpatch. New tests
cover current deployments, app/runtime/extension updates, duplicate extension
IDs in multiple branches, stale code, unverified namespaces/metadata/stores,
private environment exclusion, and retaining known update advice during partial
coverage.

The exact signed APK passed signature verification and offline installation in
a disposable adopted UEFI/KVM clone. The full live suite passed for native/procd
replacement, large ELF files, kernel inventories, Podman/pasta, sandboxed Firefox,
APK hooks and LuCI. An offline Flatpak app/runtime was built locally using a tiny
static test executable, installed from a local unsigned test repository only
inside the VM, and run under the ordinary test user. Its current deployment was
recognized. Updating that local deployment while leaving the old app running
then produced the expected close-and-relaunch advice. No external Flatpak
repositories or registry downloads were used. The corrected fixture uses the
required runtime build layout; early fixture setup errors were confined to the
disposable VM.

Publication added only the new core APK and custom-feed projection in snapshot
`20261022T140553.842203Z`, under the router's existing exact ABI
`6.18.55~628a4581533e057afecd1eb41702012b-r1`. All prior APK hashes and kernel
artifacts were preserved; existing unrelated publisher edits were retained.

| Final artifact | SHA-256 |
| --- | --- |
| openwrt-needrestart-1.0.0-r7.apk | f5ffc070eb1419ec2dd7d4601cf27a5f81611a895c547eef2e2fb84413a30e0d |
| Installed stripped scanner | ed320a74663753be95339ff8834cde7aee38cd7680c6a25073b4743825ee0d06 |

On the router, signature/hash verification and exact offline simulation passed;
only needrestart upgraded from `r6` to `r7`. A signed prior APK and ten-minute
rollback timer were prepared. Three fresh CLI scans completed in 0.80, 0.99,
and 0.79 seconds with zero warnings or restart recommendations. Fcitx5's app,
runtime and extensions were current. The LuCI queued scan also passed: 120
processes, zero unreadable processes, four containers, one Flatpak instance,
and kernel current. The rollback timer was canceled after health checks.

Boot ID `00000000-0000-4000-8000-000000000006` and running kernel
`6.18.55-owrt-628a4581533e057afecd1eb41702012b-r1-g23` were unchanged. Kernel
manager state, configuration/key hashes, checked service/network-helper/input
method PIDs, and container IDs were preserved. DNS/LuCI checks passed and
scheduled maintenance stayed inactive. No remote workload or input method was
restarted, no Flatpak deployment was changed remotely, and no reboot occurred.

Evidence and signed package:

    /srv/openwrt-validation/openwrt-needrestart-r7-validation-20261022-pxsb7hep

Remote transaction/rollback directory: `/root/needrestart-r7-20261022`.

## 2026-10-22: shared Podman networking and Flatpak proxy coverage (r9)

The renewed generic isolated-filesystem warning had two independent causes:
Podman's shared rootless bridge-network helper at PID 23220, used by the new
Compose containers, and Gear Lever's Flatpak D-Bus proxy at PID 26253. Both were
running correctly. The scanner had assumed network helpers belonged to individual
service units and that Flatpak processes shared their application's root/mount
namespace. Generic warning deduplication concealed that two processes failed
those assumptions. Previous complete scans describe the workloads active at the
time; they were not proof that every future sandbox layout was supported.

Core r8 added verified shared-helper support and PID/executable/cgroup context
to unknown-root warnings. Its signed deployment cleared the Podman case and
exposed the independent proxy case. Immutable r8 artifacts were retained; r9 is
the final package containing both corrections. Published r8 APK bytes were not overwritten.

Shared helper recognition requires an owned, non-writable-by-others, nonsymlink
PID record, an expected scope, matching UID/user namespace with a live inventoried
container whose cgroup ID still matches, the tmpfs root, and identical installed
host executable contents. Flatpak proxy recognition requires matching selected
instance metadata, UID and exact cgroup with the verified live application child,
its validated namespace/root/deployment, tmpfs proxy root and identical host
executable contents. Host mappings remain inspected for actual obsolete code.
Unknown roots still produce partial coverage, now with process context.

Source validation passed 91 compiled scanner tests, 7 ucode RPC tests, LuCI
rendering tests, package compilation, `git diff --check`, and C checkpatch with
zero errors/warnings. New regression cases cover valid shared networking and
separate proxy roots, invalid PID records/scopes/namespaces/executables/metadata,
missing containers/application children, and retained stale-library advice.
The original `.config` hash and unrelated edits were preserved.

The exact signed r9 APK passed signature verification, offline simulation and
installation in the disposable adopted UEFI/KVM clone. The full final guest suite
passed native/procd replacement, 300 MiB ELF comparisons, large kernel inventories,
APK locks/hooks/RPC, rootful/rootless/split/bridge Podman networking, real Firefox,
and an offline Flatpak with its isolated D-Bus proxy. The Flatpak fixture now
explicitly passes its session bus address into the transient user service; its
proxy must actually exist for the test to pass. Local deployment changes still
produce relaunch advice. The owned VM was powered off after validation.

Scoped publication added only core r9 and its custom-feed projection in snapshot
`20261022T153444.917596Z`, under unchanged router ABI
`6.18.55~628a4581533e057afecd1eb41702012b-r1`. All prior APK hashes and kernel
artifacts were preserved. LuCI remains r1.

| Final artifact | SHA-256 |
| --- | --- |
| openwrt-needrestart-1.0.0-r9.apk | d70add18c5c19bb6ebbc80ae6d322be1261ebfc28f7e692076d2dcb2c471462a |
| Installed stripped scanner | 19427250eb76b83614830f0f2430b003b6649b3d8b4fe6daf4b8a35a31c936f3 |

On the physical router, signature/hash checks and exact offline simulations
passed. Only needrestart changed, from original r7 through r8 to final r9.
Three fresh final scans completed in 2.18, 2.00 and 1.98 seconds: complete coverage,
zero warnings, zero unreadable processes, no restart recommendations, eight
containers, two Flatpak instances and current kernel. A queued LuCI scan also
completed with no error or warning. Timed rollback protection was canceled only
after validation and health checks.

Boot ID `00000000-0000-4000-8000-000000000006`, kernel release
`6.18.55-owrt-628a4581533e057afecd1eb41702012b-r1-g23`, kernel manager state,
configuration/key hashes, all existing checked process PIDs, and container IDs
and init PIDs were preserved. Three additional bwrap processes appeared during
the work; no original checked PID disappeared. DNS and LuCI checks passed;
scheduled maintenance stayed inactive. No workload restart, container recreation,
Flatpak update, permission relaxation or reboot was performed remotely.

Final evidence and signed package:

    /srv/openwrt-validation/openwrt-needrestart-r9-validation-20261022-ci3uim5b

Intermediate r8 evidence:

    /srv/openwrt-validation/openwrt-needrestart-r8-validation-20261022-lhqaooxf

Remote transaction/rollback directory: `/root/needrestart-r9-20261022`.
