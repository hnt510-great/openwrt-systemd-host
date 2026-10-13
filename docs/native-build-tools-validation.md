# Native build tools validation

Validated on 2026-10-13 for x86_64/glibc native-systemd firmware and a
matching physical router. Only signed local APKs were installed on the
router, using its existing trusted key and an offline APK transaction.

| Package | Version |
| --- | --- |
| flex | 2.6.4-r4 |
| bison | 3.8.2-r3 |
| bc | 1.08.2-r2 |
| pahole | 1.31-r2 |
| libdw1 (new dependency) | 0.196-r1 |

The narrow package build and complete `make -j8 V=s` build passed. The image
manifest lists these versions. APK signatures passed; all four executable
hashes on the router match the signed package payloads. The finished
SquashFS contains those same executables and Bison's C/C++ skeletons.
The root partition embedded in the compressed GPT/EFI image matches that
SquashFS, and gzip integrity and the published image checksum passed.

Image: `bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz`

SHA256: `15728529972f96671f22998d0fc74eec1119b0f1bd60d76ed4d51b9416993d5c`

`scripts/test-native-build-tools.sh` passed on the physical router without
environment overrides: Flex and Bison generated and GCC compiled a parser
that evaluated `19+23` to `42`; bc evaluated `22/7` with three decimal
places; pahole inspected a DWARF structure, added a BTF section, and read
the resulting BTF structure. Runtime checks exposed and fixed Bison's
embedded host m4 path and pahole's default LLVM objcopy dependency.

APK simulations contained only the four tools and libdw1; existing libraries
were retained. The account's existing sudo access was used. Network,
firewall and DHCP configuration hashes and the router boot ID were
unchanged. The LAN interface remained up, local DNS resolved an external
name, the existing firewall tables remained present, the router bridge
service stayed active, and LAN HTTPS returned 200. Temporary installer and
test files were removed.

No firmware was flashed and the physical router was not rebooted. The
complete new image was inspected but not cold-boot tested in this run.
These small runtime tests do not constitute a full kernel build on the
router. Unrelated local changes were preserved; nothing was committed or
pushed.

Private build and runtime logs are outside the source tree in
`/srv/openwrt-validation/native-build-tools-20261013/`; credentials are not stored
in the source or those logs.
