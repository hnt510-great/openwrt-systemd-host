# Project state and recent changes — 2026-11-14

This is a source/documentation checkpoint for `/srv/openwrt`,
inspected at main commit `c5f2bb47062a0713f22993633d40af57b05095d9`.
Since the earlier checkpoint `94715a649b29` (2026-11-04), there are 131
first-parent commits. The aggregate main-tree diff touches 833 files, including
upstream merges; these counts do not identify which agent authored changes.
Read this index with `AGENTS.md`, `CLAUDE.md` and the feature guides below.
The independent `ubuntu/openwrt` checkout is outside this review.

This checkpoint reviewed Git history, current configuration, selected source
and existing validation records. It did not rebuild, boot a VM, contact the
router, publish feeds, install packages or reboot anything. Deployment results
below are dated records, not a fresh audit of the physical router.

## Current baseline

- The target remains x86_64/glibc, signed APK, native systemd and a shared-user
  GNOME 51 desktop. The selected kernel series is Linux 7.3; the latest kernel
  update commit is `c5384e515f` (7.3.4). Older 6.18 trees remain for other targets
  and patch comparison; do not treat every upstream board fix as x86 work.
- At inspection, `.config` is byte-identical to the tracked full desktop
  snapshot, with kernel sequence 63. Both are inputs to preserve, not a reason
  to copy the snapshot over future local configuration or infer the running
  router kernel. Native artifacts remain under `bin/systemd`.
- Each `linux-image-<version>-N-openwrt` carries its kernel and selected modules;
  `kmod-*` packages hold configuration. `kernelctl` schema 2 manages parallel
  images, boot trials, blessing and default/fallback/rescue retention. Full
  builds use `build-and-publish.py build-only` to reserve/reuse numbers.
  Kernel fingerprints now ignore changes to the host system's own tools when
  deciding generations; staged build tools still matter. See
  [kernel upgrade](kernel-upgrade.md).
- Ordinary procd instances run as systemd transient services. Procd retains
  OpenWrt APIs, init-script semantics, triggers/hotplug and recovery. PID 1
  rejects direct jobs on these instances unless submitted by procd's main PID;
  root and other processes in its cgroup are not exceptions. Use LuCI,
  `/etc/init.d/NAME` or the `openwrt@NAME.service` compatibility bridge.
  See [native supervision](systemd-native-supervision.md) and
  [service bridge](systemd-service-bridge.md).

## Recent features and their evidence

| Area | Current source behavior | Existing evidence and limits |
| --- | --- | --- |
| Configuration history | `uci-history` and LuCI record revisions and timed rollback; masking now includes proxy identities and DNS API credentials. Begin/confirm a timed transaction before SSH UCI changes. | [Guide](uci-history.md), [validation](uci-history-validation.md): host/build, exact-image VM and dated router installation; not a new live state check. |
| Router audit | Read-only collector/exporter, DNS metadata, per-flow proxy dial events and minute conntrack snapshots; Debian analysis, local LLM and MCP companions. | [Guide](router-audit.md), [Debian handover](router-audit-debian.md), [validation](router-audit-validation.md). Dial events, snapshots and DNS-derived guesses have distinct meanings. |
| Installer | Hybrid BIOS/UEFI USB/optical ISO, English TUI, firstboot provisioning, ext4/btrfs/xfs overlays and optical initramfs/loop boot. | [Guide](installer-iso.md), [validation](installer-iso-validation.md): fresh VM install/boot/network/desktop matrices; physical media/firmware and Ventoy remain untested. |
| APK interruption recovery | APK r18 defers catchable commit signals, journals verified inputs under `/lib/apk/db/transaction/`, syncs writes and supports resume; `apk-transaction-guard` isolates the caller and resumes at boot. Recovery completes forward; never delete a pending journal. | [Guide](apk-transaction-recovery.md), [validation](apk-transaction-recovery-validation.md): host tests, exact-image power-cut VM and dated physical installation. No actual physical power-cut test; important VM recovery paths remain untested in that record. |
| Desktop scheduling | RealtimeKit, PipeWire realtime requests and configurable GNOME KMS scheduling; full dynamic preemption, HZ=1000 and RT group scheduling disabled by default for the desktop profile. | [Validation](rtkit-validation.md): host/build plus dated physical generation-59 checks; no VM or measured routing-latency baseline. The larger [resource governor](resource-governor-plan.md) remains a plan, not implemented policy. |
| Virtualization | OVMF UEFI, swtpm/libtpms, QEMU TPM, host-device/network-filter drivers, native AIO/io_uring, and virtio-fs host sharing/guest driver. | [Guide](libvirt.md), [UEFI/passthrough validation](libvirt-uefi-passthrough-validation.md), [virtio-fs validation](virtiofs-validation.md). VM checks and dated deployment are separate: physical PCI passthrough and the complete OpenWrt-under-libvirt-on-OpenWrt virtio-fs path are not established. |
| Wireless AP | AX101 firmware/wpad selections, LuCI tools and optional Wifi Schedule; LuCI status keeps unchanged DOM sections across polls. | [Guide](wireless-ap.md), [validation](wireless-ap-validation.md): physical 2.4 GHz AP enabled; 5 GHz blocked by NO-IR on that module/firmware. No client association/throughput or reboot acceptance; DOM test is not browser observation. |
| Google Chrome | `google-chrome-bin` stable repack with updater reading Google's apt index; selected in the desktop snapshot. | [Guide](google-chrome.md), [validation](google-chrome-validation.md): build/publication and dated physical sandboxed headless HTTPS check; interactive Wayland/GPU/audio/video not checked. |
| RDP audio and mode switches | Constant-device-latency policy, Opus preference, and r8 ownership of duplicated DMA-BUF fds prevent reuse races during monitor changes. | [Audio validation](desktop-audio-validation.md), [GNOME validation](gnome-desktop-validation.md): dated physical audio and Remmina mode-switch evidence; r8 widening/narrowing sample is small, not universal client acceptance. |
| GNOME applications and acceleration | Desktop r31 includes clipboard/core apps and XDG user directories; Mesa virtualization adds Intel/HasVK/VirtIO Vulkan ICDs, FreeRDP enables SIMD/RDPEUDP; Shell screenshot/search and PipeWire/GStreamer screencast support added. | [GNOME guide](gnome-desktop.md), [validation](gnome-desktop-validation.md): dated router installs, clipboard, live RDP Vulkan/VA-API H.264 and valid D-Bus WebM recording. Interactive Print/GUI screenshot triggering remains untested. |
| needrestart | Coverage now includes chroot services, rootless overlay mappings, Podman pod infra/helpers and Chrome zygote sandboxes. | [Guide](needrestart.md), [validation](needrestart-validation.md). Interpret process/library checks within their documented namespace and mapping limits. |

Some historical physical validation records name different CPU/GPU platforms.
Keep those observations tied to their dates and evidence; inspect hardware live
before using them to choose drivers or claim current-device compatibility.

## Publication and build workflow

Routine publication with no major behavior change or new functionality does
**not** require VM validation. Major changes and new functionality need relevant
runtime checks; use VM, device or client evidence appropriate to the behavior.
Record scope, checks and why no VM was needed. See the authoritative
[publication readiness policy](publication-readiness.md).

Keep signed immutable identities, retained-APK ELF/ucode/dependency checks,
reachable-router baseline and upgrade simulations. Pending kernel trials and
APK transaction journals block promotion. Ordinary build/publish wrappers do
not invoke a VM. The disabled scheduled runner retains its own exact-image
VM gate, frozen artifacts/hash manifests and publication retry support; that
workflow is not required for routine publication and must not be re-enabled
without a user request. See [upgrade preflight](apk-upgrade-preflight.md) and
[scheduled maintenance](scheduled-maintenance.md).

Same-version rebuild diagnosis and `allocate-rebuild-releases.py` now support
explicit ledger release allocation (`--allocate-rebuilds` on wrappers).
Unknown differences still need review. Allocation creates new package identities;
it never permits overwriting published APKs. See [LAN APK feeds](lan-apk-feeds.md).

## Repository and workspace boundaries

Feeds remain independent Git histories, with selected changes mirrored in
`patches/feeds/` and `configs/*-feeds.json`. Recent mirrors include Mesa Vulkan,
QEMU TPM/AIO, catatonit static linking, LuCI status redraw and GCC release bumps.
Argon remains `package/custom/luci-theme-argon`, a submodule (currently 3.1.4);
`package/luci-app-argon-config/` is retired untracked code to preserve.
Upstream synchronization is not GitLab publication. Inspect current refs and
remotes before any authorized commit/push; this review did not compare remote
heads. Commit feeds/child histories separately and stage explicit paths only.

Initial status contained submodule untracked content, retired nested code,
macOS metadata, a fastfetch `.claude/` directory and Python caches, with no
main-tree tracked edits. Preserve these, `.config`, overlays, keys, stashes and
all unrelated local state. Git push, signed feed publication, physical package
installation, desktop/service restart, firmware flashing and reboot remain
separate authorization and validation boundaries.
