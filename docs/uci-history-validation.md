# UCI history validation

Implementation and host validation: 2026-11-06, in this checkout. Evidence is
under `build_dir/uci-history-validation-20261106/` (generated, not committed).
No physical device was flashed. r1 and r2 were later published, and the
packages were installed on the physical router at the user's request (see
"Physical router install"); sudoers was not changed.

## Host checks

| Check | Result |
| --- | --- |
| `python3 scripts/tests/test-uci-history.py` | 24 tests pass with a temporary root and executable command shims |
| `python3 scripts/tests/test-luci-uci-history.py` | 4 tests pass using the real host ucode runtime and a stub CLI |
| `node scripts/tests/test-luci-uci-history-view.js` | Pass: revision/diff display, preview, restore/confirmation ID, no confirmation on failed connectivity, read-only controls, text escaping |
| `python3 scripts/tests/test-custom-package-updates.py` | 47 tests pass |
| Custom updater check for both new packages | Both report `local` |
| `make package/system/rpcd/clean package/system/rpcd/compile V=s` | Pass, patched rpcd release r7 |
| `make package/custom/uci-history/compile package/custom/luci-app-uci-history/compile V=s` | Pass |
| `scripts/checkpatch.pl --no-tree --no-signoff …100-ubus-uci-apply-events.patch` | 0 errors, 0 warnings |
| `make defconfig` after fragment merge | Pass; working config differs by only the two new package selections and their Chinese translation |
| Desktop snapshot | Only the feature and Chinese translation selections merged; unrelated pre-existing normalization drift preserved |
| `python3 scripts/tests/test-uci-history-vm-console.py` | 2 tests pass: a stale pre-reboot prompt cannot finish reconnection; askfirst receives only one activation newline |
| `python3 scripts/tests/test-uci-history-units.py` | 2 tests pass; complete boot graph and reproduction of the original ordering cycle |
| Image-root `systemd-analyze verify multi-user.target` | Pass with no ordering-cycle diagnostics after the path dependency fix |
| Unprivileged real CLI invocation | JSON error and exit 77 before opening history |
| `git diff --check` | Pass |

Core tests cover no-op snapshots, monotonic revisions, UCI quotes/lists/anonymous
sections and multiline strings, structured diffs and secret masking, partial
restore including creation/deletion and modes, staged-delta refusal/discard,
SSH safety, dry run, begin/confirm/abort, late confirmation, stale timer IDs,
rpcd conflicts, live event-reader attribution and expiry, APK/rollback hints,
prune numbers, denied/symlink paths, failed timer creation, failed reload retry,
boot recovery with a missing transient timer and malformed tool config, opaque
APK sidecars/nested backups, hidden extra files, explicit empty extra scope, and actual reload event
reporting from checksum lists.
The command tests verify schema envelopes, exit codes and discovery output.
All host lifecycle invocations use command shims; these prove state-machine
behavior, not real networking or systemd timer execution.

The backend tests reject shell injection, malformed revisions/config names,
invalid timeouts and empty restore selectors, enforce the output cap, preserve
CLI errors, and verify the ACL read/write split. View tests use DOM/RPC fixtures;
they do not establish real-browser rendering or end-user acceptance.

## Image and VM gate

A complete image build and exact-image KVM test are tracked separately from
the host/package results. The accepted receipt is `vm-8/validation.json`.

| Check | Result |
| --- | --- |
| Complete build-only image | Pass; kernel inputs unchanged, generation 51 reused |
| Image SHA-256 | `e4fb3ef3df0925928e36f4cbb7831767492bf797a5838649969e33f7cf952b97` |
| Exact-image router/client VM | All 10 checks pass in `vm-8/validation.json`; post-upgrade verification resumed from the retained guest disk |
| Physical-device deployment/acceptance | Not performed |

Artifact/source hashes are recorded in `artifacts.json`. The CLI hash embedded
in the tested image is `46def576eec774c69297b0cfc44e938587fd24d33d36caf197b5244f2ce96230`.
The final image was regenerated after the last CLI changes using the guarded
package compile, package install and target install paths, with updated image
metadata/checksums; the packaged CLI and rootfs CLI match the source byte for byte.

The gate is `scripts/tests/test-uci-history-vm.py`, using the existing
`scripts/test-image-network.py` disposable KVM harness. Run with immutable exact
image paths and a fresh evidence directory:

```sh
python3 scripts/tests/test-uci-history-vm.py \
  --image /absolute/path/openwrt-x86-64-generic-squashfs-combined-efi.img.gz \
  --sysupgrade-image /absolute/path/openwrt-x86-64-generic-squashfs-combined-efi.img.gz \
  --work-dir /absolute/path/new-vm-evidence-directory
```

It checks captured CLI writes, session-user apply attribution, rpcd timeout
rollback, client connectivity loss after a LAN-IP change and restored LuCI
access after timed revert, selected revision restoration, recovery across a
power cycle with an armed marker, and kept-config sysupgrade. Without
`--sysupgrade-image`, its receipt is explicitly incomplete and exit status is
nonzero. Receipts include image hashes, individual checks and scope. Guest disks
are disposable; failed disks are retained for diagnosis, and successful runs
remove only their named guest artifacts. The script has no physical-router
SSH target.

## VM evidence and verification boundary

All ten required checks are true: installed CLI matches the source hash, plain
CLI writes are captured, apply carries the session username, rpcd timeout
rollback is tagged, the client loses access after the LAN-IP change, the
independent timer restores it, the LuCI login page returns, selected restore
matches its revision, an armed transaction reverts across a power cycle, and
kept-config sysupgrade preserves the history.

Actual flashing used the existing `owrt-rescue-procd` recovery entry, as required
by this tree's sysupgrade guard. The downloaded image hash was checked again
in recovery before flashing. The guest then booted native systemd. The
pre-upgrade checkpoint used for this check is revision 14 / commit
`eceb51b6208babdd22cc365889a35e5b2e9c416a`; that commit remains in history, the
post-upgrade head is 14 and the history directory is mode 0700.

The final retention/permission check was completed on an additional native
boot of the same already-flashed guest after a console reconnection failure.
The receipt explicitly records this resumed verification. The verifier restored
the original two-NIC PCI layout and used fresh disposable OVMF variables; old
firmware variables and pre-resume receipts were backed up in the evidence
directory. This proves configuration/history retention, not preservation of
UEFI NVRAM across firmware replacement. Normal physical-device boot and client
acceptance have not been tested.

Earlier attempts are retained for diagnosis: `vm-1` exposed the login page's
normal HTTP 403 response, `vm-3`/`vm-4` exposed console framing limits, and the
full startup graph exposed a real ordering cycle in the initial path unit.
The path now has explicit dependencies without its default pre-basic ordering;
the regression tests reproduce the old cycle and reject it. The sysupgrade
probe recognizes a genuine LuCI login-required header plus HTML, preserves
failed guest disks, and activates a fresh console only once after reboot.

A failed post-flash console check can be resumed with the same image and
retained work directory using `--resume-upgrade-verification`. This requires
all preceding checks and checkpoint evidence. `--fresh-firmware` resets only
the disposable OVMF variables while saving their old contents first. Successful
runs remove only the named guest disks created by this harness.

## Post-gate review changes (2026-11-06)

Review after the first VM gate changed the CLI (r2), so the `vm-8` image's CLI
hash above no longer matches the packaged source. The changes pass the host
tests (`test-uci-history.py`, now 38 tests) and a second exact-image VM gate
(`vm-9`, below):

- Restore and transaction revert send `ubus call service event config.change`
  for each restored package that `reload_config` did not trigger. Previously a
  change applied with `/etc/init.d/network reload` (not `reload_config`) left
  reload_config's checksum baseline at the checkpoint content, so the revert
  restored the file but never reloaded the running service. The VM gate applied
  its LAN change with `reload_config` and could not observe this.
- A transaction revert signals every UCI package captured since its checkpoint,
  not only the files it rewrites. Before, a revert whose signal failed was kept
  for retry, but the retry found the files already restored and signalled
  nothing, leaving the service on the abandoned state.
- `RunningServiceRevertTest` in `test-uci-history.py` models each service's
  applied state and reload_config's checksum baseline. It covers init-script and
  reload_config applies, abort/timer/boot reverts, mixed packages, a missing
  baseline, extras, `--no-reload`, signal-failure retry, and a mutation check
  proving the scenario leaves the service broken with the pre-fix code.
  The VM gate gained `init-reload-scenario`, `init-reload-revert` (running LAN
  address and client LuCI access after a timer revert) and
  `firewall-abort-runtime` (client access after an abort of a firewall change
  applied with `/etc/init.d/firewall reload`); all three pass in `vm-9`.
  Signal-failure retry is covered by host tests only.
- An rpcd attribution hint now labels only one capture; a later unrelated
  write to the same package within thirty seconds is `external`.

### r2 exact-image VM gate

| Check | Result |
| --- | --- |
| Complete build-only image | Pass; kernel inputs unchanged, generation 51 reused (`uci-history-r2-image-build.log`) |
| Image SHA-256 | `6d66e423f3494b35adc0af76bf8363b3905ba8df81f28066b45748c2ffc0963d` (copied read-only to `image-r2/`) |
| Installed CLI SHA-256 | `c66dd6f4b00ddd917af46597768537393d4c4acd0fdafac1b688fd6ba6b9bdbd`, matching the r2 source |
| Exact-image router/client VM | All 13 checks pass in `vm-9/validation.json`, in one run without resume; guest kernel `7.3.1-51-openwrt`; kept-config sysupgrade via procd recovery, checkpoint revision 18 retained |

### Physical router install

At the user's request, `uci-history` r2, `luci-app-uci-history` r1 and rpcd r7
(with its `file`, `iwinfo`, `rpcsys` and `ucode` modules) were installed with APK
on the physical router from the LAN feeds, after a simulated transaction showed
no other changes. The APK hook recorded revision 1. rpcd was not restarted by
the upgrade and was restarted by hand to load r7 and the LuCI plugin. A
smoke test opened a 120-second transaction, committed one unused `luci` option
through rpcd's ubus `uci` API (recorded as source `ubus`, actor `operator`), and
aborted it: the option was removed, revision 3 recorded `txn-revert`, and no
transaction or revert unit remained. The abort's `reload_config` also reloaded
`firewall`, whose saved configuration already differed from procd's last-applied
baseline.

## Deliberate differences from the plan

- rpcd r6 is reserved by `configs/apk-elf-rebuilds.mk`; use r7 for changed bytes.
- Ordinary CLI writes have source `external` unless explicitly snapshotted or
  attributed within a transaction. A directory watcher cannot identify `uci`
  versus an editor. The VM gate checks this observable behavior.
- Use the full `python3` dependency, as kernelctl does: the CLI also imports uuid,
  hashlib and difflib beyond json/fcntl/subprocess, and avoids relying on the
  changing split of light modules.
- LuCI confirm/abort accept a validated transaction ID. CLI callers may also use
  `--id` to avoid accidentally finalizing a different concurrent transaction.
- Masked extra files hide their entire contents; UCI text is normalized after
  parsing, and malformed text fails closed rather than exposing raw secrets.
