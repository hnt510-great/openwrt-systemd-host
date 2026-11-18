# Upstream synchronization — 2026-11-17

Merged OpenWrt through `393efd7d74ce` (57 incoming commits) as
`44839833a8`. Independent feed merges incorporate 14 LuCI, 5 packages,
1 Passwall LuCI, 2 Passwall packages and 1 video commits. Routing, telephony
and taskplan were already current. All merges retain their previous local
HEAD as an ancestor; no reset, rebase, force update or push was used.

Preservation receipts, backup refs, incoming path inventories and kernel
application evidence are in `.git/pull-preserve/20261117T020417Z/`.
The snapshot covers 11 repositories and 135 existing local files, including
`.config`, overlays and untracked content. Stashes and unrelated nested
repositories are preserved.

## Integration and custom recipes

- Keep the Linux 7.3 `libgf128hash` mapping while adding upstream's older
  kernel ARM64 GHASH selection. Accept the other upstream crypto additions.
- Retain native-systemd procd integration and adopt upstream's `workdir`
  shell parameter support. Use `procd` release 8 rather than either side's
  release 7/3 because package contents changed.
- Keep Mesa's local desktop, VA-API and virtualization/Vulkan settings while
  accepting upstream's Panfrost and LLVM 23 patch replacements and host
  precompiler option. Advance local release 11 to 12.
- Advance hostapd release 7 to 8: incoming release 7 collides with the
  existing `wpad-mbedtls` ELF-migration reservation. Do not modify the ledger
  or overwrite the reserved identity.
- The custom updater checked 188 entries: 146 current, 36 local and 6
  requiring review. Review identified Evince 48.5 as a stable maintenance
  release in the existing 48 branch. Change its tracking policy from
  two-component `series` to `major` and update 48.4 to 48.5, preserving all
  existing package options. The source SHA-256 is
  `0c7aba9485d0b6fb9f3e0ee75be916544744dc2ed9d58a2f9936a2e0434ac4a6`,
  verified against GNOME's release checksum file. The release fixes malformed
  document handling, Synctex and viewer/shell issues; DVI remains disabled
  in this recipe. The other five review entries retain their stable pins
  (Flatpak prerelease, gcr3/GTK3 parallel major slots, Intel/IBus tag noise).

Sources: [Evince 48 releases](https://download.gnome.org/sources/evince/48/),
[48.5 changes](https://download.gnome.org/sources/evince/48/evince-48.5.news),
[checksums](https://download.gnome.org/sources/evince/48/evince-48.5.sha256sum).

## Linux 6.18 to 7.3 review

There are no incoming `target/linux/x86` changes. Two new generic patches
from upstream v7.5 affect `drivers/mmc/core/sdio.c`:

1. `445-01-v7.5-mmc-core-sdio-retry-without-UHS-if-UHS-init-fails.patch`
   (`a3838c21e28e`): reset/retry without UHS when UHS initialization fails.
2. `445-02-v7.5-mmc-core-sdio-skip-CMD11-if-signalling-is-already-1.8V.patch`
   (`67a97316a31a`): avoid an unnecessary voltage-switch command when the
   bus already signals at 1.8 V.

Both behaviors are absent from the fully patched Linux 7.3.4 source.
Forward dry runs succeed with zero fuzz and no offsets; forced reverse dry
runs fail, and sequential application to the disposable audit source succeeds.
Unlike the previous MediaTek WED candidates, these touch architecture-neutral
code enabled in this x86 configuration (`CONFIG_MMC`, `MMC_SDHCI`,
`MMC_SDHCI_PCI`, `MMC_SDHCI_ACPI`). They are recommended backport candidates
for SDIO correctness. Their benefit depends on attached SDIO devices and the
voltage/UHS conditions described by the patches; no affected physical card
or current runtime failure was established. This request's kernel work is an
applicability check: the repository's 7.3 patch stack remains unchanged.

All 354 existing 7.3 patches match their registered hashes where registered
and apply with `--fuzz=0` to a fresh extraction of SHA256-verified Linux
7.3.4 (`b11b6df8295e8e991ff040b71aaa4994a8b55caa23b6b092907f195b5840fd1f`).
The release checker reports 7.3.4 current. The three previously identified
MediaTek WED sources remain outside the selected x86 platform, as recorded
in the [previous review](mainline-kernel-patch-review.md).

The audit registry is intentionally unchanged, with 585 current 6.18 sources,
five unregistered sources (two SDIO plus the earlier three WED patches), one
previous offset-only WED source-hash change and five recorded removed sources.
It is not a hash-current registry of the incoming 6.18 stack. No additional
architecture-specific ath79/Realtek/Rockchip fixes belong in the x86 port.
The previously documented optional MAP-E finding remains open.

## Validation scope

Feed update/install, metadata regeneration, nine nonempty indexes, generated
link checks and strict Kconfig validation pass. Strict output is written to
an isolated file and has no selected-symbol differences from `.config`.
Mainline updater (20), kernel inputs (7), custom updater (49), package
metadata (4) and procd units (9) tests pass, as do both LuCI status-redraw
and firewall full-cone JavaScript checks.

The additional service-bridge suite passes 24 of 25 tests. Its staged-image
coverage test finds `apk-resume` and `wifi_schedule` missing from the adapter
list in the existing staged image. This suite result is not a runtime pass;
these source paths were not changed by the upstream merge.

Procd, Mesa, hostapd and Evince preparation pass, including retained local
patches. Target procd, Mesa virtualization and Evince builds pass. The Evince
dependency build rebuilt Mesa host tools after the incoming recipe changes.
The initial `-j3` build was interrupted to resume incrementally with `-j16`
on the 16-logical-CPU, 31 GiB host. Mesa completed its remaining target build
in about 65 seconds and Evince compiled in about 12 seconds; no swap was used
at the observed checks. Logs are `.git/sync-compile-procd-20261117.log`,
`.git/sync-compile-evince-20261117.log` (interrupted) and
`.git/sync-compile-evince-j16-20261117.log` (successful).

No firmware image was built, no VM or physical-device test was run, and no
feed publication, installation, service restart or reboot was performed.
Runtime validation is outside this source synchronization and patch review.
Merge commits are recorded separately in each repository; Evince tracking,
hostapd ledger-collision repair and this report are left uncommitted for review.

## Authorized follow-up: SDIO port and bridge coverage repair

The two SDIO patches are now carried unchanged in `backport-7.3`, with
registered hashes. All 356 patches apply with zero fuzz and the resulting
SDIO source compiles against the selected x86 kernel headers. No full kernel
or generation rebuild was performed. See the follow-up in
[the kernel review](mainline-kernel-patch-review.md).

The service-bridge coverage failure is resolved: classify `wifi_schedule` as
a setup task, exclude native-owned `apk-resume`, and direct its bridge callers
to `apk-resume.service`. The host suite now passes all 27 checks, including
real CLI/IPC rejection and task failure/completion tests. See
[the bridge validation record](systemd-service-bridge-validation.md).

### Subsequent full build and publication, 2026-11-17

The authorized full `-j16` build and coordinated publication completed as
`7.3.4-66-openwrt`. The fresh staged rootfs passes all 27 bridge tests, and
publication preflight passes. No VM or physical installation/reboot occurred.
See [the publication record](build-publication-20261117.md) for snapshot IDs,
artifact hashes, preservation checks and runtime limits.
