# x86-64 mainline kernel

The x86/64 subtarget selects Linux 7.3 instead of 6.18.55. Other x86
subtargets and other boards retain their existing kernel selection. The
versioned 6.18 configuration and patch directories remain available.

The port retains the selected router/desktop modules and built-in KVM,
including Hyper-V support. Linux 7.3 removes the nonpreemptible choice from
x86; this target uses the upstream scheduler-controlled `PREEMPT_LAZY` model.
The PHY package accommodates the renamed `mdio_bus.ko`. The downstream DT
MTD concat driver has a distinct configuration symbol so it can coexist with
the new upstream virtual-concat core.

The port keeps nfnetlink as a separately packaged module, updates the crypto,
RAID and WMI module paths, and declares the additional PHY, sound and network
module dependencies. Wireless backports remain at 7.2, release 11, with a
version-guarded include for the hex helper declarations moved in Linux 7.3.

Linux 7.3 is the final mainline release dated 2026-10-18 on
[kernel.org](https://www.kernel.org/releases.json). The source is
`https://cdn.kernel.org/pub/linux/kernel/v7.x/linux-7.3.tar.xz`; its SHA256
is `87363c24f10e06321eb362765521094e94471f6bff8bce2d6b3e40f39f004953`,
checked against kernel.org's `v7.x/sha256sums.asc`.

## Explicit synchronization

Run from this checkout:

```sh
python3 scripts/update-mainline-kernel.py --check
python3 scripts/update-mainline-kernel.py --update
```

Both commands accept `--root /path/to/checkout`. Checking is the default.
There is no integration with `scripts/feeds`, scheduled maintenance, feed
publication, or physical-device installation.

The checker compares numeric versions from kernel.org's mainline and stable
release entries. It excludes release candidates and linux-next. When the
development mainline advances to an RC, the newest final stable release
remains eligible, including its subsequent point releases. An older remote
version never downgrades this checkout.

Exit status 0 means current or successfully updated; 1 means an update is
available in check mode; 2 means a new-series port is required or an error
occurred. The JSON report identifies current/latest versions and status.

`--update` supports point releases within the already ported series. It
verifies the source archive against kernel.org's SHA256, copies the source
overlays into an isolated build directory, and applies the generic backport,
pending, hack, and x86 patch stacks in build order with zero fuzz. Only after
that succeeds does it replace the version/hash metadata. This validates
source preparation; it does not prove compilation or runtime compatibility.

An unported series such as 7.4 requires an explicit configuration, patch,
driver, build, and VM port. The updater reports `port-required` and leaves
the working kernel selected. It does not copy the previous patch stack and
claim that the new series is supported.

Updates also stop on checksum/patch errors, concurrent coordinated builds or syncs,
uncommitted edits to tracked kernel selection/version metadata, and inputs
changed during validation. Keep local edits and inspect the reported error;
do not force a metadata bump past a failed patch. A corrupt existing source
archive is reported and preserved for inspection. Failed staging directories
are temporary; tracked configuration and patch files are not rewritten.

## Build and validate

Retain the existing `.config` and normalize it after a series migration:

```sh
make defconfig
python3 scripts/build-and-publish.py build-only -j12 V=s
```

The build-only command reserves a generation for the changed kernel inputs
and builds the matching signed image, module, and development-header APKs.
It does not publish them. Do not combine a new image with modules or headers
from the previous kernel ABI.

Use the exact generated EFI image in a disposable VM with a fresh qcow2
overlay. Follow the native systemd, desktop kernel, and kernel-upgrade smoke
procedures; include a real reboot and recovery/rollback checks. Keep existing
host VMs and the physical router independent of validation. Physical
peripherals require separate hardware acceptance.

The migration's patch disposition is recorded in
[`configs/mainline-kernel-patches.json`](../configs/mainline-kernel-patches.json).
See [the validation report](mainline-kernel-validation.md) for the exact image,
source checks, guest results, and remaining physical-hardware scope.
The [patch review](mainline-kernel-patch-review.md) records compatibility findings
for optional configurations outside the validated generation-30 feature set.
