# Desktop kernel image validation

Validated on 2026-10-14 using the rebuilt x86-64/glibc native-systemd image.
The additions and package scope are described in [desktop-kernel.md](desktop-kernel.md).

A later rebuild added automatic LAN APK feed selection. Its current image
SHA256 is `a3e7dec7bf301901bf8a9713e15a85621844d94ada81ea8191e21e27d745755c`. Fresh boot,
APK hook, real reboot with a restored old feed list, and the existing native
systemd/desktop-kernel smoke checks passed. See
[LAN APK feed validation](lan-apk-feeds.md#automatic-abi-selection-validation-on-2026-10-14)
for that image and evidence. The detailed record below describes the earlier
kernel-feature image.

Firmware:

```text
bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz
SHA256: 4fe46370cef3639e5571363986957bfe82568f65dc980c729b2104709a9df39f
Size: 581054131 bytes
Kernel: 6.18.55
```

The image contains all 68 packages explicitly selected by the reusable
desktop-kernel fragment, plus their dependencies and the existing image
configuration. There are 357 installed `.ko` files. KVM, including
`CONFIG_KVM_HYPERV=y`, remains built into the kernel. The firmware uses
`kmod`/`libkmod` 32-r2 and `systemd-openwrt` release 4.

| Check | Result |
| --- | --- |
| `make target/linux/compile -j4 V=s` | Passed |
| Focused kmod and native boot bridge package builds | Passed |
| Complete firmware build, `make -j4 V=s` | Passed |
| All 78 fragment selections retained in `.config` and the stored desktop profile | Passed |
| Strict Kconfig dependency validation | Passed with the existing unrelated WeeChat cycle isolated |
| Image checksum and `profiles.json` checksum agreement | Passed |
| Signature/integrity verification of 60 kernel, selected kmod, kmod tool/library and boot bridge APKs | Passed using the image's verification keys |
| Filesystem layout and alternatives regression tests | Passed: seven Python cases and the alternatives shell checks |
| kmod module-name regression under ASan/UBSan | Passed: short names, numeric names, full paths and hyphen normalization |
| Cold boot from the exact EFI image using OVMF and a fresh qcow2 overlay | Passed; PID 1 is systemd |
| Existing native smoke test | Passed: router bridge, timers, sockets, cgroup limits, journal and router logging |
| Running kernel configuration matches the build | Passed; `/proc/config.gz` SHA256 matches the built `.config` |
| Live KVM capabilities and MSR list | Hyper-V, spinlocks and time supported; MSR `0x40000021` present |
| Diskless nested QEMU with `host,hv-time=on,hv-spinlocks=0x1fff` | Passed: CPU start, running state, stop and clean exit |
| Transient libvirt KVM guest with Hyper-V clock and spinlocks enabled | Passed: running state and cleanup |
| Representative module and built-in lookup | Passed: 42 checks, including `loop`, `8021q`, `8250`, vhost, VFIO, sound, input, Bluetooth, webcam, filesystems, USB and Intel Wi-Fi |
| Single-file modprobe configuration and alias resolution | Passed |
| `/dev/vhost-net`, `/dev/vhost-vsock`, PSI, page monitoring and THP | Present; THP defaults to `madvise` |
| APK simulation with a deliberately removed dependency index | Simulation leaves it absent |
| Signed local APK reinstall, removal and reinstallation | Hook regenerates indexes and correctly removes/restores the module entry |
| Actual GRUB procd recovery after deleting the dependency index | Passed: PID 1 is procd, LAN comes up, module lookup works, libvirt socket absent |
| Test VM shutdown and unrelated state preservation | Passed; existing host VMs remain running; unrelated source edits, index, overlays and feed changes retained |

The running kernel configuration SHA256 is:

```text
b0dc14340892201474c7ce173f8fbaed7c8ed23b087c6a750eb80964966a15c4
```

Evidence is under:

```text
/srv/openwrt-validation/openwrt-desktop-kernel-validation-20261014-133937/
```

The final image build log is `image-build-verified.log`. Final runtime
evidence is in `boot-runtime.log`, `runtime-results.json` and
`image-results.json`. The directory also contains the boot harness, sanitizer
regression, strict configuration output, package verification logs and
preservation record. Earlier image attempts remain separately named; the
results above refer to the SHA256 listed here.

The initial image tests exposed absent full-kmod indexes and freed basename
pointers in the packages feed's compatibility patch. The final image fixes
these in source, generates indexes before native/recovery module requests,
and refreshes them after APK transactions. No replacement firmware scripts
or libraries were copied into the running test image. Only test scripts and
a matching signed APK used for the package lifecycle check were transferred.

The remote router was not flashed or rebooted. These tests prove the rebuilt
image's virtual boot and the original Hyper-V CPU initialization path, not a
complete Windows installation or physical peripheral operation. Physical
audio, webcam, Bluetooth/Wi-Fi devices and PCI passthrough require testing
on their intended hardware. Sensor modules without corresponding emulated
hardware may report that they could not be probed.
