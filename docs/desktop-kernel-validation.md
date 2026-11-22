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

---

## Linux 7.3.5 generation-73 desktop & security hardening additions (2026-11-20)

Validated on 2026-11-20 after adding the P0 security/hardening, desktop/VM
compatibility, storage/firmware, audio/input, networking and tracing options to
`target/linux/x86/64/config-7.3`, `package/kernel/linux/modules/{input,netdevices,sound,video,virt}.mk`,
`configs/desktop-kernel.config`, `configs/x86-64-systemd-desktop.config`, and
`configs/x86-64-systemd-router.config`.

Firmware:

```text
bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz
SHA256: 7eaeb5813293f22c864c1859f71abbf0d4d5c9649efcc37fa567bf564d4e736a
Size: 966195475 bytes
Kernel: 7.3.5-73-openwrt
```

| Check | Scope | Result |
| --- | --- | --- |
| Linux 7.3.5 `listnewconfig` (desktop & pure-router configs) | Source | Passed: 0 unanswered Kconfig prompts |
| `python3 scripts/tests/test-systemd-router-decoupling.py` | Source | Passed: 12/12 |
| `python3 scripts/tests/test-installer-components.py` | Source | Passed: 12/12 |
| `python3 scripts/build-and-publish.py build-only -j16 V=s` | Build | Passed: generation 73 (`linux-image-7.3.5-73-openwrt-7.3.5-r73.apk`) |
| `scripts/test-image-network.py` (2-VM boot, systemd, DHCP, DNS, NAT, LuCI, ubus) | Disposable VM | Passed: 9/9 (`guest_kernel=7.3.5-73-openwrt`) |
| P0 kernel features & on-demand module probe (`p0-probe.log`) | Disposable VM | Passed: `LSM=capability,landlock,yama`, `YAMA=1`, `SOFT_WATCHDOG=1`, `/dev/ntsync`, `/dev/udmabuf`, `binfmt_misc`, `uprobe_events`; `vkms`/`snd_aloop` not auto-loaded; all 15 modules `modprobe` cleanly |
| `./scripts/publish-changed-feeds.sh` (live-router preflight + publication) | Publication | Passed: userspace snapshot `20261119T181834.019510Z`, kernel snapshot `1795112362393083342` |
| Router `apk upgrade`, `apk add` of 16 new kmods, reboot to `7.3.5-73-openwrt` | Physical router (`192.0.2.1`) | Passed: `SYSTEMD=running` (0 failed units), `kernelctl` blessed `known_good=7.3.5-73-openwrt`, `kernelctl check` passed, all 19 `/proc/config.gz` flags and 17 `modinfo` entries verified, `snd_hrtimer` active, `vkms`/`snd_aloop` not auto-loaded |

VM evidence directory:

```text
/srv/openwrt-validation/desktop-kernel-validation-20261120/
```

Scope note: Physical validation confirmed boot, systemd service health,
`kernelctl` blessing, LSM activation, `/proc/config.gz`, `/dev/ntsync`,
`/dev/udmabuf`, `binfmt_misc`, `uprobe_events`, and module presence on the
router (`7.3.5-73-openwrt`). Unattached USB HID peripherals (Logitech DJ/HID++,
PlayStation, Nintendo, Xbox controllers) were verified for module packaging and
`modprobe`/`modinfo` resolution rather than with physical controllers plugged
in.
