# Build and publication — 2026-11-17

The authorized `./scripts/build-and-publish.sh -j16 V=s --allocate-rebuilds`
completed successfully, building and publishing `7.3.4-66-openwrt`.
This includes the two carried SDIO fixes, upstream main/feed integration,
Evince 48.5 and the service-bridge coverage repair.

## Published artifacts

- Userspace snapshot: `20261117T032755.152008Z`
- Userspace ABI: `7.3.4~15132b091f127d51ea70945c4292cdd1-r1`
- Kernel snapshot: `1794886119184651350`
- Active kernel sequence: 66; channel retains image generations 64, 65 and 66.
- `public/current` and `public/kernel-upgrades` resolve to these snapshots.
- Published userspace snapshot contains 1582 packages across nine repositories,
  including retained artifacts. Its 1386 newly staged entries are a snapshot
  inventory, not the physical router's upgrade count.
- Same-version rebuild conflicts: none. The rebuild allocator made no changes.

## Validation

The full build, coordinated signature/ELF/ucode/dependency and immutable-identity
checks, reachable-router baseline and applicable upgrade simulation passed.
The simulation returned 0; it is a solver preview, not an installation.
All 27 service-bridge host tests passed against this freshly generated staged
rootfs, including native APK recovery exclusion and Wi-Fi setup-task coverage.

HTTP retrieval of all nine current repository indexes, the kernel manifest
and kernel index matches the published files byte for byte (11 checks).

The only `.config` change is `CONFIG_OPENWRT_KERNEL_SEQUENCE=65 -> 66`.
All other 134 files in the earlier protection inventory and the Git index
remain unchanged. At publication, source changes were uncommitted;
no Git push was part of that operation.

| Local artifact | SHA-256 |
| --- | --- |
| `openwrt-x86-64-generic-squashfs-combined-efi.img.gz` | `1e5d196950554321c9498187258407f8c10c981df3e6dc9f2f582cf8b844a399` |
| `openwrt-x86-64-generic-installer.iso` | `8f487ae3d0b9dd70cd234df669e125b6f0ec0b95641fba12e3a3b09143323d62` |

Artifacts are under `bin/systemd/targets/x86/64-glibc/`. Evidence is in
`/srv/openwrt-validation/build-publish-20261117T030656Z/`: `build-publish.log`, `result.json`, `bridge-tests.log`,
`http-verification.json`, `image-hashes.json` and `verification.json`.

## Runtime boundary

No VM was run solely for publication: the SDIO fixes, explicit legacy/native
service classification and compatible upstream package updates are routine
fixes within existing functionality. Source, targeted compile, full package/image
build and publication preflight checks were used. A generic VM would not prove
SDIO voltage switching/UHS behavior on physical cards.

No package was installed on the physical router, and no router service,
desktop session or host maintenance schedule was changed or restarted.
No firmware was flashed and no reboot or physical SDIO/client acceptance
was performed. Publication and runtime acceptance remain separate.

### Subsequent physical boot confirmation, 2026-11-17

After the user completed installation and reboot, a read-only SSH check found
`7.3.4-66-openwrt` running and selected as both default and known-good.
The trial counter is cleared, fallback remains `7.3.4-65-openwrt`,
`kernelctl check` returns 0 and systemd reports no failed units.
The agent did not initiate this installation or reboot. This confirms the
physical boot and built-in health checks, not SDIO voltage/UHS behavior,
Wi-Fi schedule execution or desktop/client acceptance.
