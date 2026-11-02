# Kernel packages validation, 2026-11-02

Validation of the distribution-style kernel packages described in
[kernel-upgrade.md](kernel-upgrade.md): per-build `linux-image-<release>`
packages that carry their modules, the `linux-image-openwrt` metapackage,
kernel-independent `kmod-*` configuration packages, GRUB boot counting with
automatic fallback, and the two-step migration from per-generation kernels.

## Artifacts

| Artifact | SHA-256 / identity |
| --- | --- |
| Build 46 image `openwrt-x86-64-generic-squashfs-combined-efi.img.gz` | `79778759ff4d9ba12333b907d80ee9504fbfd4294ae2988b8fd8a5401f84b574` |
| Build 47 image (same name) | `5d504065f11b7b6313f4e3ffabe393b19e374f4ff3975fcc597687d24ecfa0bc` |
| Generation 45 image (legacy model, from the daed validation) | `0541c0264fbd167e226c2d72fd0c0820307361544194ce5bbd9551587ab3ee19` |
| Kernel packages | `linux-image-7.3.1-{46,47}-openwrt` (7.3.1-r46/r47), `linux-headers-7.3.1-{46,47}-openwrt`, `linux-image-openwrt` 7.3.1-r46/r47 |
| Support packages | `openwrt-kernel-upgrade` 1-r19, `lan-apk-feeds` 6, `openwrt-needrestart` 1.0.0-r11 (source), apk-mbedtls 3.0.5-r17 (unchanged) |

Both builds were produced by `python3 scripts/build-and-publish.py build-only -j14`
with build numbers 46 and 47. The kernel configuration ABI stayed
`7.3.1~d4c77a6d354d9d21248f93d7f68211ce-r1`, so the virtual `kernel` package keeps
the same identity as the published generation 45. The rebuilt
`apk-mbedtls-3.0.5-r17` is byte-identical to the published package
(`8f2ca4c6…f55`).

## Build

| Check | Result |
| --- | --- |
| Full builds 46 and 47 through the wrapper | Passed; `package/kernel-bundle` ran before the rootfs install |
| Modules in `linux-image-7.3.1-46-openwrt` | 366 `.ko` files from all 254 selected kmods (24,974,668-byte APK); the 10 further `.ko` files in the kernel tree belong to no selected kmod |
| Rootfs | Contains `linux-image-7.3.1-46-openwrt` and `linux-image-openwrt` 7.3.1-r46, the module tree under `/usr/lib/modules/7.3.1-46-openwrt`, and kmod autoload rules in `/etc/modules.d` |
| `bzImage` release | `7.3.1-46-openwrt` (`7.3.1-47-openwrt` for build 47) |
| `scripts/test-image-network.py` on the build-47 image | Passed: native init, router services, WAN/LAN DHCP, DNS, routing/NAT, LuCI auth/HTTP, ubus |

## VM: fresh image (build 46) and upgrade to build 47

Disposable KVM/UEFI VMs (`scripts/tests/kernel-upgrade/vm-console.py`, qcow2
overlays). Build-47 packages came from a signed local repository on an extra
virtual disk. 9p sharing was not available because `kmod-9pvirtio` is not
selected in this configuration.

| Check | Result |
| --- | --- |
| First boot adoption | Schema-2 state; `7.3.1-46-openwrt` is rescue, default and known-good; `saved_entry=owrt-rescue`; dispatcher with boot counter; rescue entries before `openwrt.cfg` |
| World and retention | `kernel=<abi>` pin replaced by `kernel`, `linux-image-openwrt` enrolled; image and headers in `/etc/openwrt-kernel/protected` |
| Feeds | `lan-local.list` lists `kernel-upgrades` and nine `current/<repo>` feeds |
| Modules | 363 loaded from the package; no `/run/openwrt-kernel` overrides; no failed units |
| `apk upgrade` to build 47 | Installed `linux-image-7.3.1-47-openwrt` next to 46; `/boot/kernels/7.3.1-47-openwrt/{vmlinuz,initramfs.gz,boot.json}`; three GRUB entries; default 47 with `boot_left=3`, `fallback_entry=owrt-rescue`; both kernels retained; `kernelctl check` passed |
| Counted boot, healthy | 47 booted and was blessed: known-good 47, counter cleared, counting drop-in removed, 46 kept as fallback and rescue; still default after a further reboot |
| Counted boot, failing init injected | GRUB used three attempts, then booted 46; journal: `kernel 7.3.1-47-openwrt failed 3 boots; restored 7.3.1-46-openwrt as the default`; 47 listed as failed |
| `kernelctl set-default 47` | Rewrote a clean menu; 47 booted and became known-good |
| `kernelctl remove` | Refused for the running kernel and for the newest kernel required by `linux-image-openwrt` |
| `kernelctl install` | Re-registered an installed kernel package (recovery path) |

The VM runs found and fixed three defects:

- `apk del` exited 0 while keeping a package that the metapackage still
  required, and `kernelctl remove` trusted that exit status.
- `forget()` deleted the still-installed package's `/usr/lib/openwrt-kernel/<release>`
  metadata.
- A kernel chosen with `set-default` never became known-good.

All three are covered by host tests.

## VM: migration rehearsal (generation 45 to kernel packages)

The generation-45 image adopts with the previous kernelctl (schema 1, a legacy
rescue entry). Packages came from a signed local repository holding the build-47
kernel packages and kmods, `openwrt-kernel-upgrade` 1-r19 and `lan-apk-feeds` 6.

| Check | Result |
| --- | --- |
| Full `apk upgrade` before step 1 | Refused by the old kernelctl (`Transaction lacks matching payload`); installed database unchanged |
| Step 1 `apk upgrade --userspace-only` | Upgraded only `lan-apk-feeds` 3→6 and `openwrt-kernel-upgrade` 1-r18→1-r19; kernel unchanged; state converted to schema 2; feeds follow `current/` |
| Step 2 `apk upgrade` | Installed `linux-image-7.3.1-47-openwrt` as the counted default with the generation-45 kernel as fallback and rescue; `kmod-*` became configuration packages; `kernelctl check` passed |
| Reboot | 47 booted and was blessed on its first attempt; 363 modules; no `/run/openwrt-kernel` overrides; `kernelctl check` passed |

The first rehearsal exposed an incompatible converted health baseline. Schema 1
recorded every up interface, including DHCP WANs, so the counted boot could
never pass. It rebooted three times as designed. The conversion now keeps only
`lan`, the LAN addresses and the overlay; the second rehearsal on a fresh disk
passed.

Boots through a kernel package's bootstrap initramfs log `mount_root: failed to
launch kmodloader from internal overlay`. Modules still load and no unit fails.
This was not investigated further.

## Host tests

| Suite | Result |
| --- | --- |
| `test-kernel-bundle.py` | 8 passed |
| `test-kernel-upgrade.py` (kernelctl schema 2 and kernel channel) | 35 passed |
| `test-kernel-apk-policy.py` with a native build of APK r17 | 25 passed |
| `test-build-and-publish.py` | 61 passed |
| `test-lan-apk-publisher.py`, `test-lan-apk-client.py`, `test-lan-apk-nginx.py` | 26, 9, 1 passed |
| `test-apk-upgrade-preflight.py` | 32 passed |
| `test-needrestart.py` | 95 passed |
| Source versions, ELF ABI, merge-usr, custom updates, mainline kernel, wait-online, service bridge | 2, 23, 9, 47, 20, 14, 23 passed |

## Scope

These are build, host-test and VM results.

- **Not exercised:** the real router's exact layout (a legacy 6.18.55 rescue
  plus generation 45); conversion of that layout is covered only by host tests.
- **Not run:** the publication preflight against a router, retention beyond two
  kernels in a VM, and needrestart r11, which was not built because it is not
  selected in this configuration.
- **Not rebuilt into an image:** the `openwrt-kernel-upgrade` 1-r19 in the
  build-47 image predates the VM fixes; the rebuilt package in `bin/` has them.
  A final build is needed before publication.
- Nothing was published, and no physical device was changed.

Evidence: `/srv/openwrt-validation/kernel-packages-validation-20261102/`.
