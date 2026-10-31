# Full image build, VM validation and publication, 2026-10-29

Built the complete x86/64 glibc native-systemd GNOME firmware, including the
23 newly ported Linux 7.3 patches. Final full build exited successfully using
`scripts/build-and-publish.py build-only -j8 V=s`.

## Exact artifact

- Release: `7.3-owrt-5001c59b1072ebdf1a2ed551a854f37a-r1-g38`.
- EFI image: `openwrt-x86-64-generic-squashfs-combined-efi.img.gz` (710119230 bytes).
- SHA256: `e155822c686c43385f4a8958ce42cc4b6ebc254fbca182bb336bedd8f17e10b0`.
- The g38 image below was removed from the LAN server on 2026-10-31; the links no longer resolve.
- [Download image](http://apk.example.invalid:8088/images/7.3-g38-e155822c686c4338/openwrt-x86-64-generic-squashfs-combined-efi.img.gz). LAN access restrictions remain enabled.
- [Checksums](http://apk.example.invalid:8088/images/7.3-g38-e155822c686c4338/SHA256SUMS), [checksum signature](http://apk.example.invalid:8088/images/7.3-g38-e155822c686c4338/SHA256SUMS.sig)
  and [public verification key](http://apk.example.invalid:8088/images/7.3-g38-e155822c686c4338/image-signing.pub.pem).
  The checksum file is signed with the existing APK signing key using
  OpenSSL SHA256 signatures. HTTP-downloaded image, checksum and signature
  verification passed. No private key is included in the published directory.

## VM acceptance

The exact final compressed image was extracted into a read-only raw base and
booted via fresh qcow2 overlays with private UEFI state and isolated QEMU
networks. Both test VMs were stopped after validation.

All nine two-VM tests passed: native init, router services, WAN DHCP, LAN DHCP,
DNS, routing/NAT, LuCI HTTP, LuCI authentication and ubus board reporting.
A separate VM loaded the GNOME typelibs, settings schemas and GnuTLS backend,
passed kernelctl checks and completed a guest reboot. Initial service checks
reported no failed systemd units. This does not establish GPU/peripheral,
actual graphical desktop/RDP client or physical-router acceptance.

## Publication

- Userspace: `/srv/openwrt-feeds/public/snapshots/20261029T025919.231331Z`; 79 changed packages,
  3414 total; `same_version_rebuilds=[]`.
- Kernel: `/srv/openwrt-feeds/public/kernel-snapshots/1793242849539529628`; 1036 packages,
  2 retained image generations.
- Signed-package, ELF/ABI and router upgrade simulation/preflight passed before
  atomic feed promotion. No physical installation or reboot was performed.

Thirty-five package releases were allocated to preserve immutable published
identities. Two recipe releases were advanced beyond reserved identities.
The build selected native systemd libudev, and GJS explicitly skips GTK tests
that are not installed. The feed server now permits only approved image and
verification filenames under `/images/` via GET/HEAD, retaining LAN-only access,
private-file denial and disabled directory listing. Its configuration test and
access-control integration test passed before a graceful reload.

The original `.config` was restored byte for byte. The normalized image build
configuration and all private build/VM/publication receipts are retained under
`bin/validation/full-image-20261029/`. The pre-existing libudev provider Kconfig
cycle remains a source-metadata limitation; successful full build and VM tests
apply to the saved normalized build configuration, not a clean strict Kconfig
claim. Publication tests passed 55 cases; source-version tests passed 2 cases.
Source changes remain uncommitted.
