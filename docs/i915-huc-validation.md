# Intel HuC on Gen9–Gen11 validation

Validated on 2026-11-02. The patch was built and published as kernel
generation 48 by `scripts/build-and-publish.sh`, after the router upgrade
preflight passed. The user installed the upgrade on the physical router
(Intel N5105, Jasper Lake, device ID `4e61`) with `apk upgrade` and rebooted
into `7.3.1-48-openwrt`; the device checks below were then run over SSH,
read-only apart from a temporary encode file in `/tmp`. Gen9 and Gen10
hardware was not available.

## Artifacts

| Artifact | SHA256 |
| --- | --- |
| `target/linux/x86/patches-7.3/992-drm-i915-load-huc-on-gen9-11.patch` | `604cb2e635284a81a3c7ce5c64fead0efb960d75d15e926eb053104c0307c921` |
| `linux-image-7.3.1-48-openwrt-7.3.1-r48.apk` | `06989820370988a407f92ecc64a57d2111ff50c2ea67f07bf2a928a0a308c313` |
| `kmod-drm-i915-1000.48.7.3.1-r1.apk` | `79b43369c682f5c93cc0455f5021a38a1cd692910197a2aecdd024a48d00ae6c` |
| `i915-firmware-guc-20261019-r1.apk` | `aa65d2148004d2054eec77f8cd581b5f8c889317fddfc33ee70afb790907965c` |
| `i915-firmware-huc-20261019-r1.apk` | `118ebef7b4b63ccc50e3d050b3b11d7e36fb3c2b535f58a177304f8d39934bbe` |

Published in userspace snapshot
`/srv/openwrt-feeds/public/snapshots/20261102T083504.490251Z` and kernel
snapshot `/srv/openwrt-feeds/public/kernel-snapshots/1793608546533388403`;
receipt `/srv/openwrt-feeds/upgrade-receipts/1793608563308101386.json`.

## Build checks

| Check | Result |
| --- | --- |
| Patch against the prepared 7.3.1 tree (`patch -p1 -F0`) | Applies with zero fuzz; no other 7.3 patch touches `intel_uc.c` |
| `drivers/gpu/drm/i915/gt/uc/intel_uc.o` with the target toolchain, `W=1` | Compiles without warnings |
| 7.3.1 failure path (`__uc_init_hw`) | Missing GuC firmware in HuC-only mode returns 0 ("GuC is uninitialized"), not a probe error |
| `kmod-drm-i915` metadata | Depends on `i915-firmware-dmc`, `-guc`, `-huc` |
| `make defconfig` | Selects only `i915-firmware-guc` and `i915-firmware-huc`; snapshot updated with the same two lines |
| Full build and publication preflight | Pass (generation 48) |

## Device checks (`7.3.1-48-openwrt`)

| Check | Result |
| --- | --- |
| Packages | `kmod-drm-i915-1000.48.7.3.1-r1`, `i915-firmware-guc`/`-huc-20261019-r1` installed by the upgrade |
| `dmesg` | `GuC firmware i915/ehl_guc_70.1.1.bin version 70.1.1`, `HuC firmware i915/ehl_huc_9.0.0.bin version 9.0.0`, `HuC: authenticated for all workloads`, `GUC: submission disabled`, `GUC: SLPC disabled` |
| `debugfs …/gt/uc/huc_info` | `status: RUNNING`, HuC status `0x0007c001` |
| `/sys/module/i915/parameters/enable_guc` | `-1` (default, resolved per device) |
| `vainfo` (iHD 26.3.5) | `VAEntrypointEncSliceLP` for H.264 Main/High/CB, HEVC Main/Main10/444, VP9 profiles 0–3 |
| H.264 LP rate control | `VA_RC_CBR`, `VA_RC_VBR` advertised |
| `ffmpeg h264_vaapi -low_power 1 -rc_mode VBR -b:v 4M`, 5 s 1080p30 test source | Succeeds; 2,566,898 bytes ≈ 4.1 Mbit/s, matching the target |
| Display | i915 initialized on minor 1; fbdev `i915drmfb` is `fb0` |

Not checked: the GNOME session, a Sunshine or GNOME Remote Desktop stream end
to end, Gen9 and Gen10 GPUs, and the `i915.enable_guc=0` recovery path.

**Evidence:** command output in the session on 2026-11-02; no separate
workspace was kept.
