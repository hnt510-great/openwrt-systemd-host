# LZ4 squashfs images

The x86_64 rolling images use plain LZ4 for the normal root squashfs and the
USB/optical installer's live squashfs. This favors image-generation speed over
the smaller payloads produced by the previous XZ preset 9/extreme settings.
There is no runtime UCI setting and no change to the target `squashfs-tools`
APK.

## Scope and compatibility

`target/linux/x86/image/Makefile` overrides `SQUASHFSCOMP` only when
`CONFIG_TARGET_x86_64=y`, after `include/image.mk` has established the generic
settings. Both the normal image rule and the installer's separate squashfs rule
inherit that value. Other x86 subtargets and other architectures keep their
existing compressor selection.

The x86_64 image set also omits the redundant `rootfs.img` / `rootfs.img.gz`
artifacts. The combined BIOS/UEFI images already carry the same root squashfs;
retaining a second padded and compressed image wastes build time and storage.
The rootfs-only build rules remain available for other x86 subtargets, but are
not selected for x86_64 output.

The override deliberately contains only `lz4`: `-Xhc` selects LZ4 high
compression and defeats the build-speed goal. The existing 256 KiB blocks,
reader settings, pseudo-files, xattr policy and automatic use of all host CPUs
remain unchanged. The outer `.img.gz` and the installer's external initramfs
remain gzip-compressed; neither is part of the squashfs codec selection.

The x86_64 Linux 7.3 configuration already enables both
`CONFIG_SQUASHFS_LZ4=y` and `CONFIG_SQUASHFS_XZ=y`. Future kernels installed on
an LZ4-rootfs image must retain LZ4 support. Clean normal/failsafe images and
both installer entries use the same newly built `bzImage`, which is also the
kernel that `kernelctl` adopts as the initial rescue kernel.

A separately retained older XZ-only rescue/fallback kernel or external rescue
medium **cannot mount an LZ4 rootfs**. Failsafe does not change that constraint:
it changes boot behavior, not the kernel's available decompressors. Use rescue
media containing an LZ4-capable kernel, or reinstall an XZ image with its
matching kernel.

## Host tool

Firmware generation uses host `mksquashfs4`, not `/usr/sbin/mksquashfs` inside
the firmware. `tools/squashfs4/Makefile` enables `LZ4_SUPPORT`, and
`tools/Makefile` makes the existing `tools/lz4` static host library an explicit
prerequisite so clean builds link it in the correct order.

Rebuild and check the host tool with:

```sh
make tools/squashfs4/clean V=s
make -j16 tools/squashfs4/compile V=s
staging_dir/host/bin/mksquashfs4 -help-option -comp
staging_dir/host/bin/mksquashfs4 -help-comp lz4
```

The compressor list must include `lz4`. Enabling the target feed package's LZ4
option instead does not enable the host compressor.

## Outer combined-image compression

Native-systemd x86 images keep the `.img.gz` format but generate it with host
pigz instead of single-threaded GNU `gzip -9`. `tools/pigz` builds the pinned
2.8 release against the staged static zlib; `tools/Makefile` includes it for
`CONFIG_OPENWRT_SYSTEMD`. Other x86 configurations retain their existing
libdeflate selection, and the installer ISO and external initramfs do not use
this outer-image rule.

`Build/pigz` uses `-1 -n -p 8`. Fast mode is appropriate because the LZ4 payload
is already compressed and most remaining input is zero padding; `-n` omits file
names and timestamps for reproducibility. Eight threads matched sixteen in the
full padded-image benchmark and leaves fewer competing threads for the installer
build. The rule deliberately compresses directly instead of using
`cache-run.sh`: hashing the multi-gigabyte raw input costs more than fast pigz
compression, so both cache hits and misses were slower in the full-image test.

With the redundant rootfs-only image removed, the normal x86_64 build performs
this outer compression only for the selected combined image(s). No filename or
decompression-format change is introduced for consumers.

## Build and inspection

Generate candidates without publishing feeds or deploying to a router:

```sh
python3 scripts/build-and-publish.py build-only -j16 V=s
```

The verbose log must show plain `-comp lz4` for both the normal and installer
squashfs invocations. Inspect both filesystems:

```sh
staging_dir/host/bin/unsquashfs4 -s \
  build_dir/target-x86_64_glibc/linux-x86_64/root.squashfs
staging_dir/host/bin/unsquashfs4 -s \
  build_dir/target-x86_64_glibc/linux-x86_64/tmp/openwrt-x86-64-generic-installer.iso.squashfs
```

Both must report `Compression lz4` and 256 KiB blocks. Record exact image hashes
and test those same artifacts; an older VM receipt does not validate a newly
compressed image.

LZ4 payloads are larger. The normal x86 root partition must still fit the
payload. In the installer, p3 is stored once, described by the generated size
and SHA-256 manifest, and copied verbatim to installed p2. Guided installation
scales the ROM with the payload, so available target-disk space must account for
the larger image.

## Performance comparison

Compare compressors with the same host executable, frozen input tree and common
options. Use the previous full XZ argument string (`-Xpreset 9 -Xe -Xlc 0 -Xlp 2
-Xpb 2 -Xbcj x86`) versus plain `lz4`, retain 256 KiB blocks and four block/small
readers, and specify the same processor count for each run. Alternate repeated
pairs after a warm-up, do not run another build concurrently, and record elapsed
CPU/wall time, maximum RSS and output bytes with `/usr/bin/time -v`. Whole-build
elapsed time is not a compressor benchmark. Compare outer gzip-compatible
compressors separately on the full padded raw image; implementation, level and
thread count have very different costs. See the validation record for the
measured pigz selection and exact-image checks.

## Recovery

Remove the x86_64 `SQUASHFSCOMP := lz4` override and rebuild to return to the
existing XZ selection; the host tool retains XZ support and the x86_64 kernel
retains the XZ decompressor. Do not pair an LZ4 rootfs with an older XZ-only
kernel during recovery. Building or publishing APKs alone does not replace an
installed router's root squashfs.

Benchmark data, exact-image checks and the remaining validation scope are in
[squashfs-lz4-validation.md](squashfs-lz4-validation.md).
