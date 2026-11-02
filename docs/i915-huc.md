# Intel HuC on Gen9–Gen11 GPUs

Mainline i915 leaves GuC and HuC off on every GPU before Gen12, so Skylake
through Ice Lake / Jasper Lake (the router's N5105 is Gen11) boot without the
HuC media microcontroller. Their low-power VDENC encoders need HuC for
bitrate control, which VA-API encoders such as Sunshine and GNOME Remote
Desktop use. Without it, `VAEntrypointEncSliceLP` encoding is missing or
limited to constant QP.

`target/linux/x86/patches-7.3/992-drm-i915-load-huc-on-gen9-11.patch` changes
only the driver's default (`enable_guc=-1`):

| Graphics version | Upstream default | With this patch |
| --- | --- | --- |
| < 9 | `0` | `0` (unchanged) |
| 9–11 | `0` | `2`: load GuC only to authenticate HuC; submission stays on execlists |
| 12+ (TGL, RKL, ADL, RPL, MTL, DG2…) | per platform | unchanged |

It is adapted from coolsnowwolf/lede `x86/patches-6.18/992-enable-intel-guc.patch`,
which also turned on GuC *submission* for Gen11; upstream does not support
that, so it is not carried. An explicit `i915.enable_guc=` value still
overrides the default. The patch is recorded under `additions` in
`configs/mainline-kernel-patches.json`.

`kmod-drm-i915` now depends on `i915-firmware-guc` and `i915-firmware-huc`
(about 10 MB compressed together, every platform's blobs) next to
`i915-firmware-dmc`. If the firmware is missing, i915 logs that GuC is
uninitialized and keeps running without it, as before.

## Deployment

The patch changes the kernel, so it needs a new kernel generation; do not
rebuild a published generation with plain `make`:

```sh
python3 scripts/build-and-publish.py build-only -j12 V=s
./scripts/publish-changed-feeds.sh --dry-run
```

On the router, the APK upgrade that installs the new `kmod-drm-i915` also
installs both firmware packages. The default takes effect after booting the
new kernel.

## Check on the device

```sh
dmesg | grep -iE 'guc|huc'
# expect the ehl_guc/ehl_huc firmware loaded, "HuC: authenticated" and
# "GuC submission disabled"
cat /sys/kernel/debug/dri/*/gt*/uc/huc_info 2>/dev/null | head
vainfo 2>/dev/null | grep -E 'EncSliceLP'
```

`/sys/module/i915/parameters/enable_guc` keeps showing `-1`; the driver
resolves the default per device.

## Recovery

To return to the upstream behaviour, boot once with `i915.enable_guc=0`
added to the kernel line in GRUB (`e` on the entry). To make it persistent,
set the option for both module loaders:

```sh
echo 'options i915 enable_guc=0' >> /etc/modules.conf          # kmodloader
echo 'options i915 enable_guc=0' > /etc/modprobe.d/i915-guc.conf  # kmod/udev
```

The previous kernel generation stays available as the GRUB fallback.

See [the validation record](i915-huc-validation.md).
