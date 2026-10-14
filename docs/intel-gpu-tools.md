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

## Validation on 2026-10-15

`make -j8 package/custom/intel-gpu-tools/compile V=s` completed with the
x86_64/glibc target toolchain. Configuration normalization changed only the
selected symbol `CONFIG_PACKAGE_intel-gpu-tools=y`; the existing unrelated
WeeChat dependency-cycle warning remains. No kernel configuration changed.

Only `intel-gpu-tools-2.6-r1.apk` was published, using an isolated publisher
source directory and the existing incremental publisher. The `base` and
projected `custom` repositories received the package; all previously
published APK hashes and kernel-dependent package hashes were preserved.

On `192.0.2.1`, signed feed refresh and installation simulation selected
only `intel-gpu-tools`. Installation succeeded, and the executable hash
matched the built package. `intel_gpu_top -L` identified Intel Jasper Lake
(Gen11), with `card1` and `renderD128`. Five idle JSON samples contained all
four engine types and GPU clients. A five-second offscreen EGL workload
used `Mesa Intel(R) UHD Graphics (JSL)`; sixteen additional samples showed
Render/3D activity, nonzero GPU frequency and the Python GPU client.

Only the package and its unversioned world entry were added. The running
kernel, kernel image hash, loaded module names, boot ID, router configuration,
default route, procd state and netifd/dnsmasq PIDs were preserved. The PMU
permission setting remained `perf_event_paranoid=2`. No router reboot or
firmware flash occurred. The package is selected for future image builds;
the firmware image was not rebuilt for this package-only deployment.

Build, publication and physical-router evidence is in
`/srv/openwrt-validation/intel-gpu-top-validation-20261015/`.
