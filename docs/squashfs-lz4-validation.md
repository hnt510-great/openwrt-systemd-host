# LZ4 squashfs validation

Validated on 2026-11-21 on the Ryzen 7 5700X3D build host (16 logical CPUs),
using source revision `24d75666a1ee` plus the working-tree LZ4 patch. The
coordinated build reserved kernel sequence 78. **No feed was published, no
physical device was flashed, and the physical router was not contacted.**

## Initial LZ4/GNU-gzip candidate artifacts

The normal images are under `bin/systemd/targets/x86/64-glibc/`; the raw normal
squashfs is `build_dir/target-x86_64_glibc/linux-x86_64/root.squashfs`, and the
installer payload is the corresponding `tmp/` installer `.iso.squashfs`.
Exact copies and the complete hash list are preserved in the external evidence
directory.

| Artifact | Bytes | SHA256 |
| --- | ---: | --- |
| `openwrt-x86-64-generic-squashfs-combined-efi.img.gz` | 1312476231 | `eff3994b6bfb4863371113536266e78e2f277c09f62d51d34fba60c86459ef77` |
| `openwrt-x86-64-generic-installer.iso` | 1387479040 | `ac4d968e2107cc3157ddbeb21bfb86cbed489570f842170c54d38e96d78a012b` |
| `openwrt-x86-64-generic-squashfs-rootfs.img.gz` | 1301637639 | `80010830af9e5815957f72f24229b375c38edf9da0422ad691b13c3415f4b5ee` |
| normal `root.squashfs` | 1605707665 | `c00b8fc6cfe0b1ed07f43b50c9822eacdf4d9d172ac4d23dce31d264e55eb18a` |
| installer `.iso.squashfs` | 680445809 | `515e9d1f6f7daf60f7b27e8cd8b3bc5bc6a5628925c10c5aeff76ced0bad2e2a` |

The rootfs-only `.img.gz` above was an intermediate candidate used to measure
the redundant packaging work. The final x86_64 image selection no longer emits
it, and its current output/temporary files were removed; only external evidence
copies remain. Combined images do not depend on that artifact.

The preserved XZ combined image and ISO were 970311239 and 1099046912 bytes;
the LZ4 versions are 35.26% and 26.24% larger. The installer squashfs grew from
392021164 to 680445809 bytes (73.57%). The normal benchmark payload growth is
shown separately below.

## Source, host-tool and build checks

| Check | Result |
| --- | --- |
| `make tools/squashfs4/clean V=s && make -j16 tools/squashfs4/compile V=s` | Pass; the existing host `tools/lz4` prerequisite ran first |
| Host compile/link flags | `-DLZ4_SUPPORT` present; both `mksquashfs` and `unsquashfs` linked with `-llz4` |
| `mksquashfs4 -help-option -comp` / `-help-comp lz4` | Pass; `lz4` available, with only optional `-Xhc` shown |
| `python3 scripts/build-and-publish.py build-only -j16 V=s` | Pass in 17m42.92s; no publication |
| Normal and installer verbose build commands | Exactly two squashfs invocations; both use plain `-comp lz4`, 256 KiB blocks and no `-Xhc` |
| Normal superblock | LZ4, 262144-byte blocks, 53998 inodes; matches the refreshed build input (53997 directory entries plus the pseudo console) |
| Installer superblock | LZ4, 262144-byte blocks, 37657 inodes |
| Capacity | 1.606 GB normal payload fits the 8192 MiB root partition; 680.4 MB installer payload fits the VM's 1536 MiB ROM without a fixture change |
| `python3 scripts/tests/test-openwrt-installer.py` | 12 tests run: 11 passed, 1 skipped |
| `python3 scripts/tests/test-installer-optical.py` | 2 tests run: 1 passed, 1 skipped |
| `python3 scripts/tests/test-installer-components.py` | 12 tests passed |
| `test-installer-iso-vm.py --static-only` | Pass on the exact candidate ISO |
| `test-installer-components-vm.py --static-only` | Pass on the exact candidate ISO |
| `git diff --check` | Pass |

The full-build elapsed time includes package and kernel work and is not a
compression benchmark. No previous full-build timing is claimed as a baseline.

## Normal-rootfs compression benchmark

The input was frozen at
`/srv/openwrt-validation/squashfs-lz4-validation-20261121/frozen/root` (53999
entries, approximately 3.0 GiB). The same rebuilt squashfs-tools 4.7.5 binary
was used for every run. After one LZ4 warm-up, three XZ/LZ4 pairs alternated
order with no concurrent build. Both used 256 KiB blocks, four block readers,
four small readers, `-processors 16`, the same pseudo-files and no xattrs. XZ
used `-Xpreset 9 -Xe -Xlc 0 -Xlp 2 -Xpb 2 -Xbcj x86`; LZ4 used only `lz4`.
`/usr/bin/time -v` supplied the measurements.

| Run | Wall seconds | User seconds | System seconds | Max RSS KiB | Bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| pair1-xz | 99.250 | 1527.150 | 6.190 | 3574748 | 952029940 |
| pair1-lz4 | 1.310 | 6.450 | 3.470 | 2116444 | 1605707690 |
| pair2-xz | 99.650 | 1529.830 | 6.090 | 3459236 | 952029940 |
| pair2-lz4 | 2.060 | 6.480 | 4.560 | 2134800 | 1605707690 |
| pair3-xz | 98.750 | 1531.580 | 5.870 | 3453896 | 952029940 |
| pair3-lz4 | 1.330 | 6.460 | 3.570 | 2132896 | 1605707690 |

| Compressor | Median wall seconds | Range | Median max RSS KiB | Bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| XZ | 99.250 | 98.750–99.650 | 3459236 | 952029940 |
| LZ4 | 1.330 | 1.310–2.060 | 2132896 | 1605707690 |

Median wall-time speedup was **74.62x**, with **68.66%** payload growth. The
benchmark XZ artifact was 48 bytes larger than the preserved build-time XZ
artifact (952029940 versus 952029892 bytes); the reported growth therefore uses
only artifacts produced under the controlled benchmark, not an assumption that
separate builds are byte-identical.

## Outer combined-image compression benchmark

The raw input was reconstructed from the validated LZ4 combined image and had
8724431360 bytes with SHA256
`a408e7e8c7c6a9ba23660dea38c77937836e6d524767851b932aaafa40664271`.
It therefore included the real LZ4 payload, boot partition and zero padding.
Three rounds rotated algorithm order after a warm-up with no concurrent build.
Every benchmark output and the rebuilt-host output passed `gzip -t`; one output
per algorithm decompressed to the same raw SHA256. These are gzip-format changes
only, not changes to the raw firmware.

| Compressor | Median wall seconds | Range | Speedup | Median max RSS KiB | Bytes | Size delta |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| GNU gzip 9 | 85.960 | 84.850–86.080 | 1.00x | 1956 | 1312476231 | +0.000% |
| GNU gzip 1 | 38.130 | 37.150–39.690 | 2.25x | 1796 | 1352179741 | +3.025% |
| libdeflate 12 | 205.550 | 202.910–205.600 | 0.42x | 4529572 | 1289435019 | -1.756% |
| libdeflate 6 | 44.610 | 37.790–46.020 | 1.93x | 4701436 | 1306156827 | -0.481% |
| libdeflate 1 | 27.960 | 26.610–28.070 | 3.07x | 4390344 | 1347202624 | +2.646% |
| pigz 1, 8 threads | 8.710 | 7.990–8.740 | 9.87x | 8860 | 1352492217 | +3.049% |
| pigz 1, 16 threads | 8.730 | 7.850–8.890 | 9.85x | 15116 | 1352492217 | +3.049% |

Eight pigz threads were selected because sixteen did not improve the median and
used more memory. The newly built host pigz 2.8, linked to the staged static
zlib, produced byte-identical output to the 8-thread benchmark in 8.74 seconds
with 8812 KiB maximum RSS. The 3.049% size increase is accepted; in return the
single-image outer compression is about 9.87x faster than GNU gzip 9. The old
libdeflate 12 path was not selected: it was slower than GNU gzip on this input.
All raw timing files and per-algorithm integrity results are in the evidence
directory.

An initial cached variant was also measured and rejected. On the same raw input,
the cache-miss path took 34.18 seconds and the cache-hit path took 25.32 seconds,
versus 8.74 seconds for direct host-pigz compression. Hashing the 8.7 GB input
cost more than the compression itself. The final `Build/pigz` rule therefore
runs pigz directly and does not use `cache-run.sh`; cached and direct outputs
were verified byte-identical before removing the cache wrapper.

## Final direct-pigz artifacts and checks

The final output set was frozen under `candidate-shipping/` in the evidence
directory after the direct-pigz build. No further image build was performed
before its VM tests.

| Artifact | Bytes | SHA256 |
| --- | ---: | --- |
| `openwrt-x86-64-generic-squashfs-combined-efi.img.gz` | 1352487925 | `070ace51931c447e91ef2d79d13c8fcdc68865fd1f2d864f2186fcd2b8fa6617` |
| `openwrt-x86-64-generic-installer.iso` | 1387470848 | `503ac90373b8ddb5942d2067760878987e4961abaf017008d06041b41b614eb6` |
| normal `root.squashfs` | 1605707665 | `c00b8fc6cfe0b1ed07f43b50c9822eacdf4d9d172ac4d23dce31d264e55eb18a` |
| installer `.iso.squashfs` | 680445809 | `515e9d1f6f7daf60f7b27e8cd8b3bc5bc6a5628925c10c5aeff76ced0bad2e2a` |

Both raw squashfs hashes are identical to the initial candidates. The final
combined image is about 3.05% larger than its GNU-gzip counterpart. The ISO's
outer hash changed between focused builds, so only the final ISO above is used
for the final installer VM receipts; its raw payload remained identical.

| Check | Result |
| --- | --- |
| Final `make -j16 target/linux/install V=s` | Pass in 2m10.29s; verbose log shows direct `pigz -f -1 -n -p 8 -k -S .new`, with no `cache-run.sh` or GNU gzip 9 image command |
| Rootfs-only output selection | Pass; neither `rootfs.img.gz` nor its temporary file was regenerated in `bin/` or `tmp/` |
| Final combined gzip integrity | `gzip -t` passed on the frozen `candidate-shipping` artifact |
| Final ISO `test-installer-iso-vm.py --static-only` | Pass on SHA256 `503ac903…eb6` |
| Final ISO `test-installer-components-vm.py --static-only` | Pass on the same exact ISO |
| `python3 scripts/tests/test-build-and-publish.py` | 68 tests passed in 25.065s; no rootfs-only artifact dependency |

The 2m10.29s focused rebuild is an incremental result, not a controlled
whole-build comparison with the earlier 7m13.43s run. Cache overhead was instead
isolated by the explicit cache-hit/miss test above.

## Exact-image VM validation

### Initial LZ4/GNU-gzip candidates

| Check | Result |
| --- | --- |
| `scripts/test-image-network.py` on the exact combined image | Pass (01:15:34–01:21:06); receipt SHA256 matches `eff3994b…ef77`; native init, router services, DHCP, DNS, NAT, LuCI and ubus checks all true on `7.3.5-78-openwrt` |
| Installer UEFI USB, installation, installed-disk boot, extroot and same-build combined regression (`--case a --media usb`) | Pass (01:21:06–01:28:04); exact ISO/payload hashes match; virtual seat0/GNOME shell screenshot, LAN DHCP/LuCI/SSH, extroot and combined internal-f2fs regression all pass |
| Installer BIOS optical loop boot and installed-target verification (`--case b --media cdrom`) | Pass (01:28:04–01:31:06); exact ISO/payload hashes match; installation, installed-only boot, LAN DHCP/LuCI/SSH all pass |

### Final direct-pigz candidates

| Check | Result |
| --- | --- |
| Normal combined image `070ace5193…6617` | Pass (02:23:34–02:28:53); receipt SHA256 matches exactly; native init, router services, DHCP, DNS, NAT, LuCI and ubus all pass on `7.3.5-78-openwrt` |
| Installer UEFI USB on final ISO `503ac903…eb6` | Pass (02:28:53–02:35:44); exact ISO/payload hashes match; installation, installed-only boot, virtual GNOME seat0, LAN DHCP/LuCI/SSH, extroot and final-combined internal-f2fs regression all pass |
| Installer BIOS optical on final ISO `503ac903…eb6` | Pass (02:35:44–02:38:50); exact ISO/payload hashes match; optical boot, installation, installed-only boot and LAN DHCP/LuCI/SSH all pass |

## Evidence and scope

Evidence: `/srv/openwrt-validation/squashfs-lz4-validation-20261121/`.
It contains preserved XZ, initial LZ4 and final direct-pigz artifacts, hashes,
superblocks, frozen squashfs and padded raw-image inputs, outer-compressor and
cache-hit/miss timings, benchmark outputs, build logs and VM receipts. The
benchmark and summary scripts are retained there as well.

The validation covers host compression, image construction and disposable VMs.
It does not claim physical NIC, Wi-Fi, hardware acceleration, physical desktop
or client acceptance. Any separately retained older XZ-only rescue/fallback
kernel or external rescue medium remains unable to mount the LZ4 rootfs; the
clean image's normal, failsafe and installer entries use the matching
LZ4-capable kernel from this build.
