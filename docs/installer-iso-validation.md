# Installer ISO validation — 2026-11-07

The latest optical-compatible artifact and checks are recorded in
[Optical compatibility](#optical-compatibility--sequence-54) below. The original
USB-only sequence-53 results are retained here as the baseline.

Implementation, full build and disposable-VM acceptance completed. The guide is
[installer-iso.md](installer-iso.md); the approved design is
[installer-iso-plan.md](installer-iso-plan.md).

## Artifacts and scope

Original USB-only artifact, now preserved outside the build output:
`/srv/openwrt-validation/installer-optical-validation-20261107/usb-only.iso`.
SHA-256: `123a03d4de55f6c285a45cc42e53c3ab43aaed8e80e86618d905dd414ad4e74f`.
The final image passed the complete fresh installation matrix.
The current kernel reservation is `7.3.1-53-openwrt`.

All disk writes, service restarts and account creation in this validation are
inside disposable QEMU guests. No physical router was modified or flashed;
there was no feed publication, Git push, or host desktop restart. Original local
edits, untracked overlays, feed histories and the submodule were retained.

## Build and source checks

| Check | Result |
| --- | --- |
| Installer host suite, with an actual host-built UCI | 9 tests passed; 64 WAN/IPv6/firewall combinations applied |
| Custom-package registry suite | 47 tests passed |
| GPU coldplug shell tests | 4 tests passed |
| fstools package compile | Passed; effective APK release r5 after the existing rebuild ledger |
| Installer and desktop package compiles | Passed; final source/package payload hashes match |
| Strict Kconfig, without writing the working config | Passed |
| checkpatch, without requiring a local patch sign-off | 0 errors, 0 warnings |
| Shared ESP macro versus original recipe | Byte-identical combined EFI disk images, including BIOS setup; same inputs and fixed FAT directory clock |
| Real sparse-file GPT with p1/p2/p3/p128 | Passed; BIOS region starts at sector 34 |
| USB boot spike: OVMF/NVMe, SeaBIOS/SATA, OVMF/virtio | All passed; source p3 root, tmpfs overlay, installer target and physical NICs |
| Full build-only | Sequence 53 completed, including the IPv6 first-boot fix; the reserved kernel was reused |
| Serial TUI walkthrough | Reached all screens and default-No confirmation; then completed an ext4 install on the virtual disk |
| Installed ext4 overlay, ESP and kernelctl | Passed on the disk booted alone |
| User creation and sudo group | Passed |
| GNOME coldplug integration | Bound bochs DRM exposed an unnecessary modprobe failure; source fix passed in the VM, with seat0/tty7 session and no failed units |
| Final fresh ISO matrix and client acceptance | See matrix below |

## Final image VM matrix

Every installation attaches the exact ISO as a USB storage device and a new
16 GiB target. Each installed system is then booted with the USB absent.

| Case | Firmware / target / overlay | Settings | Result |
| --- | --- | --- | --- |
| a | OVMF / NVMe / ext4 | WAN DHCP, IPv6 on, regular user and GNOME | Passed, including rendered GNOME screenshot and kernelctl bootstrap modules |
| b | SeaBIOS / SATA / btrfs | Static WAN, IPv6 off | Passed, including IPv6 policy after stock first-boot defaults |
| c | OVMF / virtio / xfs | PPPoE configuration, full-cone NAT | Passed; actual full-cone NAT rules verified |

All three cases have p3 overlays, p1 `/boot`, working `kernelctl`, no failed
units, no personal account or proxy nodes, and no remaining firstboot request.
Their separate LAN clients obtain leases inside the requested pool, log into
LuCI over HTTPS with status 200, and authenticate over SSH with the chosen root
password. PPPoE acceptance is configuration-only; no PPPoE server is provided.

The final image also passed an extroot regression: a cloned installation booted
with an independent ext4 `/dev/vda1` overlay, retained a preservation marker,
and kept its NVMe boot partition. The same build's normal combined image also booted successfully with its internal F2FS overlay.

The full configuration snapshot was refreshed from the accepted build's
`.config`, preserving its pre-existing local selections. Changes against the
original working configuration are limited to the installer selections and
kernel reservation; the committed snapshot was already older than that working
configuration.

## Findings incorporated into the implementation

- sfdisk needs `first-lba: 34` and an explicit numeric `128 :` entry to create
  the BIOS partition while retaining boot/rom/overlay as partitions 1/2/3.
- Tracked defaults must be normalized with `merge-usr.py` before copying them
  into the pristine package root, whose `/lib` is already a symlink.
- Mount ISO9660 from media partition 1; opening the whole disk conflicts with
  its already mounted p3 root. A VM confirmed p1 exposes `install/esp` and the
  manifest correctly.
- PCI driver coldplug comes from udev. The installer only falls back to
  kmodloader if physical NICs are absent, and optional hardware probe failures
  are nonfatal. Zero-capacity block devices are excluded from disk selection.
- Stock whiptail does not bind Escape. A terminal relay adds Escape cancellation
  while preserving CSI/SS3 arrow keys, without changing feed packages. A real
  terminal test exercises both navigation and Escape.
- The confirmation is a readable list of actual partition sizes and selected
  settings. Passwords and hashes are omitted; PPPoE configuration is mode 0600.
- Preseed the stock odhcpd global section so its first-boot defaults do not
  overwrite the selected IPv6 policy. A host regression runs the actual
  `odhcpd.defaults` with IPv6 and DHCP independently enabled/disabled.
- Desktop coldplug skips PCI GPUs that already have a driver, avoiding a fatal
  alias lookup for built-in bochs DRM while retaining probes for unbound GPUs.

## Evidence

Private evidence directory outside the repository:
`/srv/openwrt-validation/installer-validation-20261107/`.

`ipv6-build.log` is the successful final build-only receipt for sequence 53.
The earlier full-build logs retain the diagnosed usr-merge failure and its
successful repair. `installer-host-tests.log`, `desktop-coldplug-tests.log`,
`custom-package-tests.log`, `fstools-checkpatch.log` and `strict-final.log`
record source checks. `final-source-hashes.txt` confirms that the source
installer payload and GPU coldplug script match the final package root;
`kernel-image-hashes.txt` records the identical bzImage, package and ESP kernels.

`verified-vm/receipt.json` and its per-case command/serial logs are the final ISO
matrix evidence; `verified-vm/a/gnome.png` records the rendered GNOME desktop.
`esp-regression-release/result.txt` and `esp-release-reproduce.py` reproduce the
same-input combined EFI byte comparison after the final rebuild.

`boot-spike/` and `spike-vm-3/receipt.json` record the separate sequence-52 USB
boot proof. `manual-tui/serial.raw` records a full interactive installation.
`final-manual-tui/serial.raw` records every serial-console TUI screen, Escape
navigation and the default-No confirmation leaving the target unpartitioned;
that walkthrough preceded the final backend-only odhcpd fix, with unchanged TUI
payload. `manual-installed-diagnostic.log` and `manual-gnome-check.log` retain
the original GPU alias diagnosis and its successful VM repair.

## Remaining hardware acceptance

Physical USB media, firmware compatibility and networking on the actual PC have
not been tested. PPPoE was validated as configuration only. All completed boot,
desktop and client checks above are disposable-VM results.

## linux2024 virtual-machine follow-up — 2026-11-07

The user's local `qemu:///system` VM used the exact final ISO (SHA-256 matched),
but attached it as a SATA CD-ROM with the target disk first in boot order. Its
VirtIO 3D display also returned `no surface` to a QEMU screenshot request.
The original optical-media configuration cannot expose the appended p3 as the
PARTUUID-addressable live-root disk required by this USB-only image.

After explicit authorization, the VM was shut down and restarted with the ISO
as a read-only raw USB disk first in boot order and standard VGA with SPICE GL
disabled. The installer welcome screen rendered, and a Down key moved the
selection from Install to Open shell; Up returned it to Install. No installation
or formatting was invoked. The two changes were applied together, so this check
does not isolate a separate VirtIO 3D display defect. Other VMs were untouched.

Original/proposed XML and rendered screenshots are retained under the private
evidence directory's `linux2024/` subdirectory. The guide now includes explicit
virt-manager/libvirt USB attachment instructions. Optical ISO boot was unsupported by that original implementation; the amendment
below adds it.

## Optical compatibility — sequence 54

Current artifact:
`bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-installer.iso`.
SHA-256: `916a75b77b997aa3e1631f6012f2e872f8a43cf3b7e1bb3f5e2a97e2d1fc4628`.
Kernel: `7.3.1-54-openwrt`; installer package: `1-r2`.

The installer now loads a small external initramfs from both GRUB entries. It
keeps the USB PARTUUID/p3 root path. For SATA optical media it checks the image
MBR signature, p3 type/offset and squashfs magic, maps the same appended payload
read-only as `/dev/loop0`, and switches into normal preinit with the tmpfs overlay.
The installer accepts that optical source only if the loop and its backing
optical device are read-only. The manifest/ESP mount uses the whole CD rather
than a fictitious CD partition. The payload is not duplicated.

The bootstrap builder resolves absolute target symlinks inside the target tree,
recursively freezes ELF dependencies without executing target code on the host,
and reuses kernelctl's deterministic newc writer. It checks required built-in
kernel features and fails the build if they are absent. It does not change the
installed system's boot flow.

| Check | Result |
| --- | --- |
| Installer host suite | 9 passed, including actual odhcpd defaults |
| Optical source safety and bootstrap execution | 2 passed; actual archive extracted, tools executed under target loader/libraries, deterministic bytes checked |
| Custom-package registry | 47 passed |
| Full build-only | Passed; reserved sequence 54 |
| bzImage / packaged kernel / installer ESP kernel | Identical SHA-256 |
| Early optical bootstrap probe | Passed; read-only `/rom` on loop0 backed by sr0 |
| Final GRUB optical installation matrix | Passed: all three cases below |
| Final extroot regression | Passed; cloned installation uses separate ext4 overlay and retains marker |
| Final USB/XFS installation and combined F2FS regression | Passed, including DHCP, HTTPS login, SSH password and full-cone rules |
| Additional USB boot matrix | Passed: OVMF/NVMe, SeaBIOS/SATA, OVMF/virtio |

The final ISO was attached as a read-only **SATA CD-ROM**, booted through its
actual GRUB entries, and installed to new 16 GiB targets:

| Firmware / target / overlay | Configuration and result |
| --- | --- |
| OVMF / NVMe / ext4 | Passed: WAN DHCP, IPv6 on, sudo user, rendered GNOME session, kernelctl bootstrap modules |
| SeaBIOS / SATA / btrfs | Passed: static WAN, IPv6 off retained after first boot |
| OVMF / virtio / xfs | Passed: PPPoE settings and full-cone rules; PPPoE server not supplied |

Every case then booted its target disk **without the ISO**, checked p3 overlay,
p1 `/boot`, kernel version/kernelctl, no failed units, completed firstboot and
absence of personal accounts/proxy nodes. Separate LAN clients obtained DHCP
leases in the requested pool, authenticated to LuCI over HTTPS (200) and to SSH
using the selected root password. Installer screenshots are retained in each
case's `installer.png`; the ext4 user's rendered desktop is `a/gnome.png`.

The same ISO passed all three USB boot combinations and a complete USB/XFS
installation with client acceptance. The same build's normal combined image
retained its internal F2FS overlay. A clone of the optical/ext4 installation
retained its marker while booting from an independent ext4 extroot. The full
configuration snapshot now matches the accepted build; only kernel sequence
53 -> 54 changed against the working config preserved before this amendment.

Evidence is private and outside the repository:
`/srv/openwrt-validation/installer-optical-validation-20261107/`.
The final build is `build.log`; host checks are `installer-tests.log`,
`final-optical-tests.log` and `registry-tests.log`; `kernel-hashes.txt` records
the kernel equality check. `bootstrap-probe/` is an early direct-kernel probe
against the original sequence-53 payload, distinct from the final ISO tests.
Final receipts and serial/command logs are in `cdrom-vm/`, `usb-vm/` and
`usb-boot-vm/`.

The user's running linux2024 VM and its currently attached original ISO were
left unchanged during this amendment. There was no feed publication, push or
physical-device deployment. Physical optical drives and Ventoy are untested.
