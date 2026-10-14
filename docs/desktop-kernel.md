# Desktop kernel support

The x86-64 native-systemd desktop image includes the selections in
`configs/desktop-kernel.config`. They are also merged into the existing
`configs/x86-64-systemd-desktop.config` and build `.config`; existing package
and router settings are retained.

The additions cover vhost network and virtual-socket acceleration, VFIO PCI,
HDA analog/HDMI and USB audio, HID multitouch and userspace input, USB
Bluetooth, Intel Wi-Fi, UVC webcams, removable-media filesystems, SMB/NFS/9p
clients, USB serial/printers/Ethernet and temperature monitoring. Drivers use
normal OpenWrt kmod packaging and module loading. Existing Intel graphics,
VirtIO, SATA/NVMe, networking, FUSE and XFS support remain available.

The Intel wireless firmware set covers 7265D, 8265, 9260, AX200/201/210/411
and BE200; Bluetooth firmware covers Intel and RTL8761BU. Other hardware may
need its matching firmware. Kernel drivers alone do not configure Wi-Fi,
Bluetooth pairing, desktop audio sessions or guest Windows VirtIO drivers.

`CONFIG_KVM_HYPERV=y` is set in `target/linux/x86/64/config-6.18`. This is
host-side Hyper-V emulation for Windows guests, separate from the existing
Hyper-V guest drivers. Without it, the Windows preset's `hv-time=on` causes
QEMU to abort while setting MSR `0x40000021`. See the
[QEMU Hyper-V documentation](https://www.qemu.org/docs/master/system/i386/hyperv.html).
KVM remains built into the kernel for both Intel and AMD processors.

The image also enables performance counters, task/I/O accounting, pressure
stall information, process page monitoring, kprobes/BPF tracing and huge
pages. Transparent huge pages default to `madvise`, and no reserved huge-page
pool is configured. `kmod-ikconfig` exposes the actual running kernel config
at `/proc/config.gz`. VFIO requires IOMMU protection; unsafe no-IOMMU support
remains disabled. No host PCI device is assigned automatically.

New kmod definitions provide `kmod-hid-multitouch` and `kmod-vhost-vsock`.
The vsock package explicitly disables the unselected packet-monitor driver,
so enabling the transport does not leave an unanswered kernel configuration
prompt during the build.

Full kmod tools use dependency/alias indexes. Native early init generates
them after mounting the overlay and before starting systemd; procd recovery
generates them before normal module loading. An APK post-commit hook refreshes
them after online package transactions, including removal. Offline image
assembly does not execute target binaries. Procd still owns device events
and the normal OpenWrt module loading sequence.

Native images preserve kernel paths in `modules.builtin` so full kmod also
recognizes built-in modules whose names start with digits. The packages feed
repair in `patches/feeds/0008-packages-kmod-glibc.patch` fixes three freed
basename pointers in kmod 32's compatibility patch. Provenance is recorded in
`configs/desktop-kernel-feeds.json`. Both `kmod` and `libkmod` use release r2.

Build and inspect:

```sh
make defconfig
make target/linux/compile -j4 V=s
make -j4 V=s
```

Native firmware and matching signed packages are under `bin/systemd`.
After booting a disposable VM from the rebuilt EFI image, run
`python3 /tmp/desktop-kernel-smoke.py` using the script from
`scripts/tests/desktop-kernel-smoke.py`. It queries the running KVM API,
loads representative modules and starts a diskless, networkless nested QEMU
with the same Hyper-V CPU flags as the failed Windows VM. A passing result
proves that startup path; it does not prove a complete Windows installation
or operation of unconnected physical peripherals.

See [desktop-kernel-validation.md](desktop-kernel-validation.md) for the
rebuilt image identity and validation results.
