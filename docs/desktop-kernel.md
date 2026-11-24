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

`CONFIG_KVM_HYPERV=y` is set in `target/linux/x86/64/config-7.3`. This is
host-side Hyper-V emulation for Windows guests, separate from the existing
Hyper-V guest drivers. Without it, the Windows preset's `hv-time=on` causes
QEMU to abort while setting MSR `0x40000021`. See the
[QEMU Hyper-V documentation](https://www.qemu.org/docs/master/system/i386/hyperv.html).
KVM remains built into the kernel for both Intel and AMD processors.

`CONFIG_IA32_EMULATION=y` is also set there, with
`CONFIG_IA32_EMULATION_DEFAULT_DISABLED` unset, so 32-bit x86 programs run
without an `ia32_emulation=` boot argument. Steam needs this because its client
and runtime include i386 binaries; the Flatpak Steam package supplies its own
32-bit libraries, so the host still has no i386 userspace. The legacy x32 ABI
and the iptables 32-bit compatibility layer stay disabled. Because enabling this
option changes the kernel ABI, it requires a new kernel generation and a reboot.

The image also enables performance counters, task/I/O accounting, pressure
stall information, process page monitoring, kprobes/BPF tracing and huge
pages. Transparent huge pages default to `madvise`, and no reserved huge-page
pool is configured. `kmod-ikconfig` exposes the actual running kernel config
at `/proc/config.gz`. VFIO requires IOMMU protection; unsafe no-IOMMU support
remains disabled. No host PCI device is assigned automatically.

New kmod definitions provide `kmod-hid-multitouch`, `kmod-vhost-vsock`,
`kmod-drm-vkms`, `kmod-sound-hrtimer`, `kmod-sound-aloop`,
`kmod-input-ff-memless`, `kmod-hid-logitech`, `kmod-hid-playstation`,
`kmod-hid-nintendo`, `kmod-input-xpad`, `kmod-tap`, and `kmod-macvtap`.
`kmod-vhost-vsock` explicitly disables the unselected packet-monitor driver, and
`kmod-input-xpad` explicitly disables unselected legacy joystick drivers, so
enabling them does not leave unanswered kernel configuration prompts during the
build. `kmod-drm-vkms` and `kmod-sound-aloop` intentionally omit `AUTOLOAD` so
they are loaded on demand (`modprobe vkms` / `modprobe snd-aloop`) without
adding a virtual DRM display or audio sink at boot. `kmod-vhost-net` declares a
conditional `+PACKAGE_kmod-tap:kmod-tap` dependency when `CONFIG_TAP` is built
for `kmod-macvtap`.

In Linux 7.3 (`target/linux/x86/64/config-7.3` plus `configs/desktop-kernel.config`
and `configs/x86-64-systemd-router.config`), the x86-64 baseline also enables:

- **Security and hardening**: `CONFIG_SECURITY=y`, `CONFIG_SECURITYFS=y`,
  `CONFIG_SECURITY_LANDLOCK=y`, `CONFIG_SECURITY_YAMA=y` (default
  `CONFIG_LSM="landlock,lockdown,yama,loadpin,safesetid,ipe,bpf"`),
  `CONFIG_RANDOMIZE_BASE=y` / `CONFIG_RANDOMIZE_MEMORY=y` (KASLR), and
  `CONFIG_KERNEL_CC_STACKPROTECTOR_STRONG=y`.
- **Desktop/VM/container runtime & storage**: `CONFIG_BLK_WBT=y` /
  `CONFIG_BLK_WBT_MQ=y`, `CONFIG_BINFMT_MISC=y`, `CONFIG_USERFAULTFD=y` /
  `CONFIG_PTE_MARKER_UFFD_WP=y`, `CONFIG_NTSYNC=y`, `CONFIG_UDMABUF=y`,
  `CONFIG_FW_LOADER_COMPRESS=y` (`XZ` + `ZSTD`), `CONFIG_FUSE_PASSTHROUGH=y` /
  `CONFIG_FUSE_IO_URING=y`, `CONFIG_SQUASHFS_ZSTD=y` / `CONFIG_SQUASHFS_LZ4=y`,
  `CONFIG_NTFS3_LZX_XPRESS=y`, and `CONFIG_SND_HDA_RECONFIG=y` /
  `CONFIG_SND_HDA_PATCH_LOADER=y` in `kmod-sound-hda-core`.
- **Diagnostics & networking**: `CONFIG_UPROBES=y` / `CONFIG_UPROBE_EVENTS=y`,
  `CONFIG_KERNEL_SOFTLOCKUP_DETECTOR=y`, `CONFIG_KERNEL_CGROUP_PERF=y`, and
  `kmod-macvlan`, `kmod-macvtap`, `kmod-ipvlan`, `kmod-dummy`, `kmod-tls`,
  `kmod-unix-diag`, `kmod-packet-diag`.

Full kmod tools (`kmod` 34.3) use dependency/alias indexes. Native early init
generates them after mounting the overlay and before starting systemd. An APK
post-commit hook refreshes them after online package transactions, including
removal. Offline image assembly does not execute target binaries. `systemd-udevd`
owns raw device events and forwards `/etc/hotplug.d` handlers to procd, while
OpenWrt retains its normal module loading sequence.

Native images preserve kernel paths in `modules.builtin` so full kmod also
recognizes built-in modules whose names start with digits.

Build and inspect (reserving a kernel generation without publishing):

```sh
make defconfig
python3 scripts/build-and-publish.py build-only -j12 V=s
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
