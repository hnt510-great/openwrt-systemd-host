# Intel HuC on Gen9–Gen11 validation

Validated on 2026-11-02 on the build host only. **No kernel generation was
built, reserved or published**, no image was built or booted, and no physical
device was touched. Runtime behaviour on the N5105 is still unverified.

## Artifacts

| Artifact | SHA256 |
| --- | --- |
| `target/linux/x86/patches-7.3/992-drm-i915-load-huc-on-gen9-11.patch` | `604cb2e635284a81a3c7ce5c64fead0efb960d75d15e926eb053104c0307c921` |
| `bin/systemd/packages/x86_64/base/i915-firmware-guc-20261019-r1.apk` | `aa65d2148004d2054eec77f8cd581b5f8c889317fddfc33ee70afb790907965c` |
| `bin/systemd/packages/x86_64/base/i915-firmware-huc-20261019-r1.apk` | `118ebef7b4b63ccc50e3d050b3b11d7e36fb3c2b535f58a177304f8d39934bbe` |

## Checks

| Check | Result |
| --- | --- |
| Patch against the prepared 7.3.1 tree (`patch -p1 -F0`) | Applies with zero fuzz; no other 7.3 patch touches `intel_uc.c` |
| `drivers/gpu/drm/i915/gt/uc/intel_uc.o` with the target toolchain, `W=1` | Compiles without warnings; the tree was reverted afterwards |
| 7.3.1 failure path (`__uc_init_hw`) | Missing GuC firmware with HuC-only mode returns 0 ("GuC is uninitialized"), not a probe error |
| `make package/firmware/linux-firmware/compile` | Pass; Jasper Lake blobs `ehl_guc_70.1.1.bin` and `ehl_huc_9.0.0.bin` are in the source |
| `kmod-drm-i915` metadata after `make package/kernel/linux/compile` | Depends on `i915-firmware-dmc`, `-guc`, `-huc` |
| `make defconfig` | Selects only `i915-firmware-guc` and `i915-firmware-huc`; snapshot updated with the same two lines |
| Published identity | That local `kmod-drm-i915-1000.47.7.3.1-r1.apk` differed from published generation 47, so the published bytes (`9fa4548b…`) were restored in `bin/`; the change ships only in the next reserved generation |

Not checked: a full kernel build, HuC authentication and VDENC encoding on
the N5105, Gen9/Gen10 hardware, and the APK upgrade path.

**Evidence:** command output in the session on 2026-11-02; no separate
workspace was kept.
