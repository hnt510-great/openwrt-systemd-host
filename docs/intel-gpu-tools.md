# Intel GPU usage monitoring

Select `CONFIG_PACKAGE_intel-gpu-tools=y` on the x86_64/glibc target with
`CONFIG_KERNEL_PERF_EVENTS=y`. The desktop configuration includes it; the
standalone selection is in `configs/intel-gpu-tools.config`.

The package builds `intel_gpu_top` from upstream IGT GPU Tools 2.6 using the
target toolchain. It ships the monitor and license, without driver tests or
the shared IGT test library. Existing DRM, PCI, udev and GLib libraries supply
its runtime dependencies. Cairo, pixman, libdw and libkmod are needed only by
the upstream build configuration.

Build and publish using the matching signed LAN feed:

```sh
make package/custom/intel-gpu-tools/compile V=s
./scripts/publish-changed-feeds.sh --dry-run
./scripts/publish-changed-feeds.sh
```

Review the publisher preview before publishing other pending builds. On the
router, refresh the feed and simulate the installation first:

```sh
sudo apk update
sudo apk add --simulate intel-gpu-tools
sudo apk add intel-gpu-tools
sudo intel_gpu_top -L
sudo intel_gpu_top
```

The monitor displays engine utilization (Render/3D, Blitter, Video and
VideoEnhance), GPU frequency and available power counters. Individual
counters depend on the GPU and kernel driver. Use root access for PMU reads;
no persistent change to `perf_event_paranoid` is needed.

For five one-second JSON samples:

```sh
sudo intel_gpu_top -J -s 1000 -n 5 -o -
```

Upstream sources and documentation:
[IGT GPU Tools](https://gitlab.freedesktop.org/drm/igt-gpu-tools) and
[release archives](https://xorg.freedesktop.org/archive/individual/app/).

## Historical validation note (2026-10-15)

Initial build and physical checks passed for `intel-gpu-tools` (current recipe
`2.6-r4`) on an Intel Jasper Lake (Gen11) host (`intel_gpu_top -L`, idle and
offscreen EGL JSON sampling across Render/3D, Blitter, Video, and VideoEnhance
engines). Evidence: `/srv/openwrt-validation/intel-gpu-top-validation-20261015/`.
