# Linux 7.3 mainline validation

Completed 2026-10-24 for the x86/64, glibc, native-systemd desktop configuration.
This report covers source preparation, a complete firmware build, and disposable
VM tests. It does not authorize or report live feed publication or router flashing.

## Source and artifacts

The selected final release is Linux 7.3, released 2026-10-18 according to
[kernel.org](https://www.kernel.org/releases.json). Its source archive SHA256 is
`87363c24f10e06321eb362765521094e94471f6bff8bce2d6b3e40f39f004953`,
verified against kernel.org's `v7.x/sha256sums.asc`.

The completed build used:

```sh
python3 scripts/build-and-publish.py build-only -j12 V=s
```

The running release was
`7.3-owrt-5001c59b1072ebdf1a2ed551a854f37a-r1-g30`; the OpenWrt kernel ABI was
`7.3~5001c59b1072ebdf1a2ed551a854f37a-r1`. Generation 30 is a local build;
the live feed remained at generation 25.

Artifacts are in `bin/systemd/targets/x86/64-glibc/`. SHA256 values:

| Artifact | SHA256 |
| --- | --- |
| `openwrt-x86-64-generic-squashfs-combined-efi.img.gz` | `d8e4e568980b0a54a0efb22a3f66b0f8685c68c72130d3d1917f4ddfa1d55181` |
| `openwrt-x86-64-generic-squashfs-rootfs.img.gz` | `60da1f958e039dee73659ce398246ca8a2a40241838044b15b8ac9e033c35a4e` |
| Compiled `arch/x86/boot/bzImage` | `bda166865f98e2a01a4c2d1b5349c7ae67996135c48f3c77dbdc7eedfebba7a7` |
| Prepared kernel `.config` | `894d2485adae6abba82c635a73ec6ad6facdabe04ff63d610f0c2817132aca2a` |
| Immutable generation-30 image APK | `adbddf5368f3f5f1bbdee976e7d23fcc35d540cbee978f9b46966eca634198d6` |
| Immutable generation-30 development-header APK | `9ab81ea21456f040384247b3f108f391fcb6fb1194e37bc9b02a7d1850ed0082` |

The APK names include the complete release above. The private test repository
contained 519 signed packages. Projection checked the selected image, kernel ABI,
logical module/header trackers, immutable payloads, and exact dependency closure.
Every previously selected package remained selected. Normalization added
`kmod-phy-package`, `kmod-net-selftests`, and the existing `kmod-nf-log6`
compatibility selection.

## Source checks

The initial audit classified all 481 original kernel patches: 193 as upstream,
two as superseded, and 286 as carried. The subsequent
[patch review](mainline-kernel-patch-review.md) corrects one upstream classification
and records three issues in optional features disabled in this configuration.
With the additional nfnetlink modularity
patch, all 287 patches apply with zero fuzz. Original and ported patch SHA256
values match `configs/mainline-kernel-patches.json`; the 6.18 files remain intact.

Both the working configuration and saved desktop profile pass strict
`conf --fatalrecursive` normalization. The updater's live `--check` returned
`current=7.3`, `latest=7.3`, `status=current`. `git diff --check` passes.

| Test suite | Passing tests |
| --- | ---: |
| Mainline updater | 20 |
| Kernel input selection | 7 |
| Build/publication coordinator | 47 |
| Kernel upgrade manager | 54 |
| APK kernel policy | 21 |
| Custom package updater | 39 |
| Total | 188 |

The APK policy tests used the actual patched target APK executable and its
matching libraries in disposable test roots. Checkpatch was run on rebased C
patches; carried patches retain legacy style/signature diagnostics. The new
nfnetlink and wireless compatibility patches pass their focused checkpatch runs.

## Exact-image VM results

The EFI image above was extracted without modification and used through private
qcow2 overlays. Guests used KVM, private firmware variables, and isolated QEMU
networking. No physical router or existing host VM was used as a test guest.

The fresh-image guest reported the exact generation-30 release. Its decompressed
`/proc/config.gz` matched the prepared kernel configuration SHA256 above.

- Native systemd PID 1, merged `/usr`, router services, D-Bus, timer/socket
  activation, cgroup memory/PID limits, journald and router logging passed.
- All 42 desktop smoke-test modules loaded. KVM capabilities, Hyper-V reference
  TSC MSR support, diskless nested QEMU startup, and transient libvirt startup passed.
- Native GCC compiled an external module against the installed generation-30
  development headers. Its vermagic matched the running kernel; load and unload
  succeeded.
- A real Podman container passed PID-namespace, seccomp-mode, and read-only-root
  checks with networking disabled. A separate user-namespace check passed.
- SSH and SFTP worked. A normal reboot changed the boot ID and retained the
  generation-30 kernel, matching configuration, LAN, SSH, and systemd smoke results.
- Bridge creation/deletion and the BPDU-filter sysfs flag round trip passed.
  No kernel warning was reported by the focused boot-log check.
- The GRUB procd recovery entry booted the same 7.3 kernel with procd as PID 1.
  LAN, SSH, module loading, and the kernel configuration hash passed there too.

The separate two-VM network test passed all nine required checks: native init,
router services, WAN DHCP, LAN DHCP, DNS, routing/NAT, LuCI HTTP, LuCI
authentication, and ubus board reporting. Its receipt records the exact EFI image
SHA256 above. Personal external integrations were disabled only inside those
disposable guests for the isolated network fixture.

## Cross-version upgrade and rollback

A fresh overlay of the original 6.18.55 generation-25 image adopted its legacy
rescue generation. The guest verified all 519 signed test APKs. The APK support
upgrade was simulated first, then installed offline. The subsequent kernel
upgrade simulation left the world file, package database, and kernel state hashes
unchanged. The identical offline transaction then installed the complete 7.3
image/module/header closure and armed the generation-30 trial.

The real trial boot passed the normal continuous health checks and promoted
generation 30 to known-good. A subsequent `kernelctl rollback` and real reboot
returned to 6.18.55, with generation 30 recorded as previous-good. LAN, SSH,
`kernelctl check`, network/system configuration hashes, and the original rescue
kernel hash all passed after rollback.

An earlier generation-29 VM test caught bridge registration failing because the
carried BPDU-filter attribute exceeded Linux 7.3's rtnetlink slave-array bound.
The trial was not promoted and successfully returned to its protected 6.18 rescue.
The port now increases that bound; generation 30 passed the full repeated image,
network, trial, and recovery tests. Generation 29 was retained only as private
diagnostic evidence.

## Preservation and limits

Final comparisons found no changes to the protected image overlays, feed
definitions, signing-key identities, feed repository heads/status/stashes, root
HEAD, staged changes, or stashes. The live channel symlink and manifest SHA256
remained unchanged. Disposable test VMs were stopped after validation.

Physical GPU, audio, wireless, storage, and network devices still require their
own hardware acceptance. Module loading and virtual-device tests do not establish
physical peripheral operation or physical-router performance. No live feed was
published and no physical device was installed, flashed, or rebooted.

Detailed private evidence is retained in
`/srv/openwrt-validation/openwrt-mainline-20261024-084724/`, including
`image-build-9.log`, `final-artifacts.json`, `preservation-final.json`,
`vm-network-final/validation.json`, and the `vm-clean/` and `vm-upgrade-final/`
logs and receipts.

The subsequent authorized publication and physical-router installation, without
a reboot, are recorded in [the deployment report](mainline-kernel-deployment-20261024.md).
