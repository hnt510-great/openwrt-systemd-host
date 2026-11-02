# Early CPU microcode for kernel packages

`intel-microcode` (and `amd64-microcode`, when selected) installs CPU microcode
under `/usr/lib/firmware/{intel,amd}-ucode/`. Before this change the only
loader was the preinit hook
`target/linux/x86/base-files/lib/preinit/02_load_x86_ucode`, which asks the
running kernel for a *late* reload. That never works on this tree:

- The x86/64 kernel sets `CONFIG_MICROCODE_LATE_FORCE_MINREV=y`, so late
  loading refuses any update whose header does not declare a minimum
  revision. Intel's files generally do not declare one.
- Even a successful late load comes after the kernel has chosen its
  speculative-execution mitigations, so it cannot fix them.

On the router (Celeron N5105, signature `06-9c-00`) the log showed
`microcode: Unsafe microcode update: Microcode header does not specify a
required min version`. The CPU stayed on revision `0x1d`, although the package
ships `0x24000026`, and `srbds`, `reg_file_data_sampling`, `mmio_stale_data`
and `old_microcode` were reported as vulnerable for lack of microcode.

## Early loading through kernelctl

Kernel packages already boot through a kernelctl-built initrd, so
`kernelctl` now writes a second file next to each generation's bootstrap:

```
/boot/kernels/<release>/microcode.cpio    uncompressed newc cpio
    kernel/x86/microcode/GenuineIntel.bin  (or AuthenticAMD.bin)
/boot/kernels/<release>/initramfs.gz      bootstrap, unchanged
```

The GRUB entries list it first:

```
initrd /boot/kernels/<release>/microcode.cpio /boot/kernels/<release>/initramfs.gz
```

GRUB concatenates the two files. The kernel's early loader reads the leading
uncompressed archive, and the initramfs unpacker then reads both. The layout
is the same one Debian and dracut use.

- **Running CPU only.** The archive holds just the file the kernel would look
  up for the running CPU (`intel-ucode/FF-MM-SS`, or
  `amd-ucode/microcode_amd_famXXh.bin`), about 20 KB. All Intel files would
  add 23 MB to each generation on a 128 MB `/boot`. If the disk is moved to
  another CPU, the early loader finds no match and boots as before, and
  the next kernel install or microcode change writes the right file.
- **No update, no file.** If no file matches the CPU, no `microcode.cpio` is
  written and the entry keeps its single initrd.
- **Microcode changes follow automatically.** After every successful,
  non-simulated APK transaction, `kernelctl apk-post` compares each package
  kernel's `microcode.cpio` with the installed microcode and replaces,
  removes or adds it, then updates `boot.json`, `state.json` and
  `/boot/grub/openwrt.cfg`. The bootstrap `initramfs.gz` is not rebuilt.
  For a userspace-only transaction, a failure only prints
  `kernelctl: early microcode not refreshed: …` and does not fail APK.
- **The file is part of the boot inventory.** `kernelctl check` verifies it
  like the other boot files. A refresh verifies every other boot file first,
  so it repairs an interrupted refresh but refuses to work on a changed
  kernel or bootstrap.
- **Rescue entries are unchanged.** The original image kernel is booted with
  `noinitrd` and stays on the firmware-provided revision. It is the
  fallback if a microcode update ever misbehaves.
- **Preinit late reload is kept.** It is harmless and covers kernels whose
  configuration allows it.

The kernel already has `CONFIG_MICROCODE=y` and `CONFIG_BLK_DEV_INITRD=y`, so
this needs no new kernel generation. It ships in `openwrt-kernel-upgrade`
`1-r21`.

## Deployment

Upgrade `openwrt-kernel-upgrade` on the router through the normal feed.
The APK transaction that installs it runs the new `kernelctl apk-post`, which
adds `microcode.cpio` to the installed generations. To do it by hand:

```sh
kernelctl microcode      # prints "updated" or "current"
grep initrd /boot/grub/openwrt.cfg
```

The new revision takes effect at the next boot of a package kernel.

## Check on the device

```sh
dmesg | grep -i microcode
# expect "microcode: Updated early from: 0x0000001d" and
# "Current revision: 0x24000026", and no "Running old microcode"
grep . /sys/devices/system/cpu/vulnerabilities/{srbds,reg_file_data_sampling,mmio_stale_data,old_microcode}
```

## Recovery

- Choose another generation or the rescue entry in GRUB; the rescue kernel
  never loads early microcode.
- To boot a generation once without the update, press `e` in GRUB and
  delete the `microcode.cpio` path from the `initrd` line.
- To stop shipping it, remove the microcode package (`apk del intel-microcode`).
  The same transaction removes `microcode.cpio` from every generation.

See [kernel packages and upgrades](kernel-upgrade.md) and
[the validation record](early-microcode-validation.md).
