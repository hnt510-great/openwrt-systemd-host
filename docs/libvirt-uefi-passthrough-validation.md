# Libvirt UEFI, vTPM, passthrough and network filter validation

Validated on 2026-11-11 for x86_64/glibc native-systemd OpenWrt. Guide:
[libvirt.md](libvirt.md).

## Image and packages

| Item | Value |
|---|---|
| Image | `bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz` |
| SHA256 | `121bc5cdc89664ed8fb7ca7681137d947de7dbcb0a38cd46e3e99d6410181924` |
| Build | `python3 scripts/build-and-publish.py build-only -j12`, kernel sequence 59 (unchanged inputs, no new kernel generation) |
| Packages | libvirt/virsh/libvirt-daemon `12.9.0-r2`, QEMU `11.1.3-r2` (`CONFIG_QEMU_TPM=y`), `swtpm 0.10.2-r1`, `libtpms 0.10.2-r1`, `ovmf-bin 2026.08-r1` (Debian `ovmf-generic 2026.08+ds-3`), virt-manager `5.1.0-r4`, OpenSSL `3.5.9-r5` (Camellia enabled for libtpms) |

Host checks: the libvirt meson summary reports Node device and NWFilter
drivers enabled, Network and Interface disabled, and
`firewall_backend_priority: nftables`. QEMU's configure reports TPM support,
and the binary contains the `tpm-crb`, `tpm-tis` and `tpm-emulator` devices.
`scripts/update-custom-packages.py --check --package` passes for `libtpms`,
`swtpm` and `ovmf-bin`, `scripts/tests/test-custom-package-updates.py` passes
(47 tests), and `git diff --check` passes for the main tree and packages feed.

## Disposable nested VM checks

The exact image boots as a disposable L1 KVM guest (UEFI, 6 GiB) with an
emulated Intel IOMMU (`intel-iommu,intremap=on`), a spare e1000e NIC, a QEMU
XHCI controller with a USB tablet (0627:0001), and an isolated LAN socket.
Personal Passwall/WAN integrations are disabled as in
`scripts/test-image-network.py`. Inside it, libvirt runs L2 fixture guests
that boot this build's kernel with a busybox initramfs and print what they
see on a file-backed serial console.

`intel_iommu=on iommu=pt` was added once to the GRUB entries in
`/boot/grub/grub.cfg` as the guide describes, and the L1 VM was rebooted.

| Check | Result |
|---|---|
| IOMMU active after the documented GRUB step | Pass: arguments on `/proc/cmdline`, 9 IOMMU groups |
| `virt-host-validate qemu` | Pass: no FAIL lines; hardware virtualization and `/dev/kvm` pass. The IOMMU line warns because the check looks for AMD IVRS on this AMD CPU while the L1 IOMMU is an emulated Intel DMAR |
| `scripts/tests/test-libvirt-secondary-drivers.py` on the target | Pass: 5 tests (network/interface report `VIR_ERR_NO_SUPPORT`; node devices, default nwfilters and UEFI/vTPM domain capabilities present) |
| Domain capabilities | Pass: `efi`, `secureBoot`, `enrolledKeys`, the three OVMF code images, TPM `tpm-crb`/`tpm-tis` with the `emulator` backend |
| Secure Boot guest with Microsoft keys | Pass: running; loader `OVMF_CODE_4M.ms.fd` `secure='yes'`, nvram from `OVMF_VARS_4M.ms.fd`, `<smm state='on'/>` |
| swtpm process | Pass: runs as `swtpm` with its socket under `/run/libvirt/qemu/swtpm` |
| Persistent TPM, CA and nvram paths | Pass: `tpm2-00.permall`, swtpm-localca `issuercert.pem`, `fixture-sb_VARS.fd` under `/srv/libvirt/state` |
| UEFI guest sees the TPM | Pass: L2 reports EFI and an ACPI `TPM2` table |
| Node devices | Pass: `nodedev-list` shows the PCI devices, including the spare NIC, and USB devices |
| PCI passthrough | Pass: host driver is `vfio-pci` while running; L2 lists e1000e 8086:10d3 |
| USB passthrough | Pass: L2 lists 0627:0001 |
| PCI device returned | Pass: host driver is `e1000e` again after the guest stops |
| `clean-traffic` guest on `br-lan` | Pass: DHCP lease 192.0.2.120 from OpenWrt dnsmasq, ping to 192.0.2.1 works |
| Spoofed source address | Pass: ping from an added 192.0.2.222 is blocked. Control without `<filterref>` on the same VM: the spoofed ping succeeds |
| nwfilter tables | Pass: `bridge libvirt_nwfilter_ethernet`/`inet` appear next to `inet fw4` and survive `fw4 reload` |
| firewall4 untouched | Pass: stateless `nft -s list table inet fw4` hash equal before the guest and after it plus `fw4 reload` |
| State across L1 reboot | Pass: the Secure Boot/TPM guest starts again with the same TPM state and CA |
| `virsh undefine --nvram --tpm` | Pass: TPM state directory and nvram file removed |

Two defects found during this validation were fixed before the final image:
`swtpm` could not read its configuration files (they were installed 0600 root,
now 0644), and it could not create its control socket because
`/run/libvirt/qemu` was 0750 `libvirt-qemu` (now 0751, traverse only).
Earlier harness topology and output-size errors are recorded with the evidence.

## Scope

This was nested AMD KVM validation with an emulated Intel IOMMU and emulated
devices. No physical device was flashed, no physical PCI/USB device was passed
through, and no APKs were published. A Windows 11 installation and a signed
operating system boot under Secure Boot were not tested; the Secure Boot check
proves firmware selection, key enrollment template and SMM, and that the guest
runs. virt-manager's GUI was not exercised; its UEFI default comes from
`virtinst`'s OS-database logic after removing the local SeaBIOS-only override.

## Publication

Published on 2026-11-11 with `scripts/publish-changed-feeds.sh` after a
passing `--dry-run`. The router upgrade simulation against the installed
router passed with no blockers and 24 package changes; the kernel feed was
unchanged. Userspace snapshot:
`/srv/openwrt-feeds/public/snapshots/20261111T094927.952546Z`. The first dry
run rejected `native-libs-dev 1-r7` because its bundled
`openssl/configuration.h` changed with Camellia; it was republished as
`1-r8`.

## Router deployment

On 2026-11-11 the router (Intel Celeron N5105) was upgraded with `apk upgrade`
from that feed: exactly the 24 simulated changes, with no guests running.
Libvirt units were restarted, the new `virtnodedevd`/`virtnwfilterd` sockets
listen, and `virt-manager-setup router-admin` granted the account access to them.
On the router, `scripts/tests/test-libvirt-secondary-drivers.py` passes all 5
tests, `virsh nodedev-list` lists PCI and USB devices and `virsh
nwfilter-list` lists the default filters. The services needrestart reported for
the replaced `libcrypto.so.3` (haproxy, ttyd, router-audit-collect,
uci-history-events, sshd, the GNOME desktop, gnome-remote-desktop and Sunshine)
were restarted; an already open SSH login kept the old library until logout.

The firmware publishes a DMAR table (VT-d enabled), but the kernel ran without
`intel_iommu=on`, so `virt-host-validate` warned. `intel_iommu=on iommu=pt` was
added to the systemd and procd entries of kernels 59 and 56 in
`/boot/grub/openwrt.cfg` (backup `openwrt.cfg.pre-iommu`; failsafe and rescue
entries unchanged). It takes effect at the next reboot, which has not been done
in this record, so PCI passthrough on the router is not yet verified.

## Evidence

`/srv/openwrt-validation/libvirt-uefi-validation-20261111/`: `run-vm-test.py`,
`build-fixture.sh`, fixture `init`/domain XML and `fixture/SHA256SUMS`,
`run5/receipt.json` (all 18 checks), `run5/router.commands.log`,
`run5/router.serial.log`, `control-no-filter.log`, and the failed earlier runs
(`run1-failed-harness`, `run2-failed-assertion`, `run3`, `run4`).
