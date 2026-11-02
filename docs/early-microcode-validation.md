# Early CPU microcode validation

Validated on 2026-11-02 on the build host, then on the router.
`openwrt-kernel-upgrade` `1-r21` was published at the user's request with
`publish-changed-feeds.sh` (userspace snapshot `20261102T092342.144276Z`, no
new kernel generation); the user upgraded and rebooted the router.

## Artifacts

| Artifact | SHA256 |
| --- | --- |
| `bin/systemd/packages/x86_64/base/openwrt-kernel-upgrade-1-r21.apk` | `a6b7c984e432f02f4436ad5b8f3a79964ce72c2e37dd116a9986da9a73329b6d` |
| QEMU kernel `build_dir/target-x86_64_glibc/linux-x86_64/bzImage` (7.3.1) | `23bc76ef97a176e687df79159074a46ba92e9b2702714f0ef2310afe2f1240c3` |
| `microcode.cpio` for `06-9c-00` from `intel-microcode` 20260925 | `3e411e33171eee7d964a15f96f15ab30622ca7577c39bb90c3c7d7634f6b0d5d` |

## Checks

| Check | Result |
| --- | --- |
| Router state before the change (read-only SSH, kernel `7.3.1-48-openwrt`) | Revision `0x1d`; `06-9c-00` holds `0x24000026`; late reload refused ("does not specify a required min version"); `srbds`, `reg_file_data_sampling`, `mmio_stale_data` and `old_microcode` vulnerable |
| `python3 scripts/tests/test-kernel-upgrade.py` | 41 tests pass, 5 of them new: running-CPU selection, three GRUB entries with `microcode.cpio` first, no file without a match, AMD family container, follow/remove on APK changes, no change for simulated or `--no-scripts` transactions, repair of an interrupted refresh, refusal on a changed bootstrap |
| Archive layout against the host's Debian `initrd.img-7.2-amd64` | Same newc entries (`.`, `kernel`, `kernel/x86`, `kernel/x86/microcode`, `<Vendor>.bin`), uncompressed, first in the initrd |
| QEMU TCG, `-cpu Snowridge,family=6,model=156,stepping=0,-hypervisor`, initrd = `microcode.cpio` + gzip bootstrap | The kernel unpacks both archives and executes `/init` from the gzip part. TCG ignores microcode writes, so the early load itself cannot be observed there |
| `make package/custom/openwrt-kernel-upgrade/compile V=s` | Pass; the packaged `kernelctl` is byte-identical to `files/kernelctl` |
| `git diff --check` | Clean |

## Router after upgrade

Read-only SSH check on 2026-11-02, Celeron N5105, booted kernel
`7.3.1-48-openwrt` (running, default, known-good):

| Check | Result |
| --- | --- |
| APK upgrade path | `apk-post` wrote `microcode.cpio` (21504 bytes) to generations 47 and 48 and updated their `boot.json` |
| `/boot/grub/openwrt.cfg` | Both generations: `initrd …/microcode.cpio …/initramfs.gz` |
| `dmesg` | `microcode: Current revision: 0x24000026`, `Updated early from: 0x0000001d`; no "Running old microcode" or late-load refusal |
| `old_microcode` | `Not affected` (was `Vulnerable`) |
| `reg_file_data_sampling` | `Mitigation: Clear Register File` (was `Vulnerable: No microcode`) |
| `mmio_stale_data` | `Mitigation: Clear CPU buffers; SMT disabled` (was `Vulnerable … no microcode`) |
| `srbds` | Still `Vulnerable: No microcode`. Linux 7.3 marks Jasper Lake as affected through `MMIO_SBDS`, and the mitigation needs `SRBDS_CTRL`. The newest available revision, `0x24000026`, does not report it (no `srbds_ctrl` flag), so microcode loading cannot change this |

Not checked: generation 47 booting with microcode, and AMD hardware.

**Evidence:** `/srv/openwrt-validation/early-microcode-validation-20261102/`
(archive, QEMU initrd and console log, test output, `router-after-upgrade.txt`).
