# Native mainline kernel build validation

Validation workspace: `/srv/openwrt-validation/kernel-native-validation-20261014/`.
This test uses an isolated OpenWrt VM and does not change the physical router.

## Input and VM

- Initial systemd/glibc image SHA256:
  `93396580545011e04cd8a2c641f8d30f304984c877400d4b69cb27a467284707`.
- QEMU/KVM: 12 host CPU vCPUs, 10240 MiB RAM, private firmware overlay,
  separate 64 GiB NVMe build disk formatted as ext4.
- Network: QEMU user networking; SSH forwarded only to `127.0.0.1:22514`.
- PID 1: systemd; native GCC 14.4.0, libelf 0.196, OpenSSL 3.5.9.
- Source cloned inside the VM from Torvalds' mainline repository:
  `https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git`.
- Tested commit: `4056b3c9d3c92ea45955641dbafeb9b960e146ef` (`7.3-rc7`).
- Build configuration: unmodified `make ARCH=x86_64 x86_64_defconfig`.
- Parallel build: `make -j12 ARCH=x86_64`.

## Missing development files

The first defconfig failed in `scripts/kconfig/conf.c`:

```text
error: 'PATH_MAX' undeclared here (not in a function)
```

The installed native GCC private `include/limits.h` contained only
`glimits.h`. Its standard `limitx.h`/`limity.h` wrapper was absent, so it did
not include `syslimits.h` and the target libc `<limits.h>`. The glibc header
itself was present. Native GCC release 8 reconstructs the standard upstream
wrapper when packaging the target compiler; it does not import host headers.
After that fix `PATH_MAX=4096`, defconfig succeeded, and the extended native
build-tools smoke script passed without compiler/environment overrides.

The initial image already contained ELF/libelf/gelf, OpenSSL, zlib, libc and
Linux UAPI headers, unversioned linker names, and pkg-config metadata. Bash,
GNU make/binutils, flex/bison/m4, bc, pahole, Git HTTPS/CA certificates, Python,
GNU awk, compression tools, and Perl File/Getopt modules were also present.
The reusable `configs/native-build-tools.config` now explicitly selects these
native-build dependencies, all of which were already enabled in the desktop
image. Static `libc.a` was absent and was not needed by the complete defconfig
build. No additional runtime libraries or third-party headers were missing.

## Acceptance

The initial full build passed after applying the header fix inside the VM.
It produced an ELF64 x86-64 `vmlinux`, `arch/x86/boot/bzImage`, `System.map`,
and 12 loadable modules. Kernel release: `7.3.0-rc7-g4056b3c9d3c9`.
Defconfig SHA256: `a84d80a45beac93c90c9bc08c5ee427daf6bd47667676e737668db5af81f49c1`.
Initial bzImage SHA256: `4bbad1fbe69896cc38256a92e3824ea0e9f29921283679d7b4027f3de80b400e`.

The native GCC package build (`make -j12 package/feeds/packages/gcc/compile V=s`)
and complete image build (`make -j12 V=s`) passed. The signed
`gcc-14.4.0-r8.apk` passed `apk verify` with this checkout's public key.
APK SHA256: `cb9eb7d1e1e564b3a89519ddf71066747fea483a4523a95d0afbd667ddf1c0d5`.

Final image: `bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz`.
SHA256: `32d3ff003c75f2c653f7db8c5cfbd4319e93e8edb28ce6026283df3256fe4d30`; matches the generated `sha256sums`.

The rebuilt image was cold-booted with a fresh firmware overlay and no APK
upgrades or copied headers. Its installed GCC release 8 limits header matched
the rebuilt signed package (SHA256
`0b52c077c3c6520d73b6124ff94dcd05b8d2da681bdbeffc05b8697d11f46b11`).

| Check on rebuilt image | Result |
| --- | --- |
| systemd PID 1 and 12 vCPUs | Passed |
| Native limits, lexer/parser, bc, DWARF and BTF smoke | Passed |
| Native development headers, pkg-config, C/C++ linking and library API smoke | Passed |
| Router bridge, timers, sockets, cgroup limits, journal/logread smoke | Passed |
| Clean mainline defconfig kernel and modules, `-j12` | Passed in 226.0 seconds |
| Defconfig identical to initial run | Passed, byte-for-byte |
| ELF64 x86-64 vmlinux, bzImage and 12 modules | Passed |
| Post-build router services and OOM check | Active; no OOM events |

The initial source tree was cleaned with `make mrproper`; the final build
used a new `O=/srv/kernel-build/final-build` directory. No source/config
workarounds or disabled kernel features were used. Final artifact checksums:

```text
a84d80a45beac93c90c9bc08c5ee427daf6bd47667676e737668db5af81f49c1  .config
f956d7f47ee2a2bd7d217b6d16bb39977494273cfdf7107a3c03db970c000e41  arch/x86/boot/bzImage
51a1258ade65a77a8c510700c0e30ecac070a7050112d7e4a42a4c8e06c14399  vmlinux
80203545510633e9c6d77398d21d0ef9b1b7bca96d4cee5f511d1f35aea30ba5  System.map
```

Evidence includes `image-build.log`, `gcc-package-build.log`,
`final-validation-resumed.log`, `build-final.log`, `kernel-final-timing.json`,
and the three `*-final.log` smoke logs in the validation workspace. The host
also retains a copy of `bzImage`, `System.map`, and `kernel-final.config`.
After a shutdown/restart, systemd, GCC release 8, the retained bzImage hash,
router services and mainline Git HTTPS access were verified again; evidence
is in `builder-ready.log` and `builder-after-reboot.log`.
The original OpenWrt `.config` and pre-existing desktop-profile edits were
verified byte-for-byte against their pre-task snapshots.

## Retained builder VM

The final-image VM is running with 12 vCPUs, 10 GiB RAM, its private boot
volume and 64 GiB ext4 build disk. Its build artifacts are under
`/srv/kernel-build/final-build`; the mainline Git clone is under
`/srv/kernel-build/linux`. SSH is forwarded to `127.0.0.1:22514` and accepts
only the generated validation key for unattended access.

Use the helper in the validation workspace:

```sh
cd /srv/openwrt-validation/kernel-native-validation-20261014
python3 builder.py run 'cd /srv/kernel-build/linux; make -j12 ARCH=x86_64 O=/srv/kernel-build/final-build'
python3 builder.py stop
# To start again after stopping:
python3 builder.py start
```

`builder.py start` mounts the retained build disk and sets the VM-only NAT
gateway/DNS through UCI for future Git access. It does not change host or
physical-router networking.

Building a mainline kernel does not
install it or claim it boots with the OpenWrt root filesystem. BTF is disabled
by this defconfig; the native pahole smoke test independently covers BTF.
