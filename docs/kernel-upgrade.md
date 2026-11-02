# Kernel packages and upgrades on x86 native-systemd OpenWrt

Kernels are installed and upgraded the way Debian, Fedora and similar
distributions do it:

- every kernel build is its own package, `linux-image-<release>`, carrying the
  kernel and **all of its modules**;
- several kernels are installed side by side, and `apk upgrade` installs the
  newest one next to the running kernel;
- installing a kernel builds its initramfs and GRUB entry (the equivalent of
  `kernel-install`/`update-grub`), and the newest kernel becomes the GRUB default;
- the new kernel runs after you reboot. GRUB gives it three attempts and then
  falls back to the previous kernel;
- userspace no longer depends on the kernel version.

The image's original kernel (`/boot/vmlinuz`) is never written. It stays as the
rescue entry, together with procd recovery and failsafe entries. GRUB's core is
not reinstalled, and no disk is flashed.

Validation of this model is recorded in
[the kernel package validation report](kernel-packages-validation.md).

## Packages

For kernel build number N of Linux version V the build produces:

| Package | Version | Contents |
| --- | --- | --- |
| `linux-image-V-N-openwrt` | `V-rN` | vmlinuz, config, System.map and every selected module under `/usr/lib/modules/V-N-openwrt/` |
| `linux-headers-V-N-openwrt` | `V-rN` | prepared headers for on-device module builds (when `kernel-dev-headers` is selected) |
| `linux-image-openwrt` | `V-rN` | metapackage: always depends on the newest `linux-image-*` |
| `kernel-dev-headers` | `1000.N.V…` | metapackage for the newest headers |
| `kmod-*` | `1000.N.V-r…` | autoload (`/etc/modules.d`), `modprobe.d` rules and dependencies only |

`uname -r` is `V-N-openwrt`, for example `7.3.1-46-openwrt`. N is the build
number, which the build wrapper reserves. The OpenWrt configuration hash no
longer appears in the release, and patch-only rebuilds are ordinary new kernels.

Module binaries ship in the kernel package, so a `kmod-*` package only enables
autoloading. A module that was not selected when the running kernel was built
becomes available after the next kernel build that includes it and a reboot into
that kernel. The bundled modules are the ones selected in `.config` (about 376
`.ko` files from 254 kmods in the current profile).

## Build and publish

```sh
./scripts/build-and-publish.sh -j16      # build and publish
python3 scripts/build-and-publish.py build-only -j12 V=s   # build, do not publish
./scripts/publish-changed-feeds.sh [--dry-run]             # publish a completed build
```

The wrapper fingerprints the kernel's inputs (kernel and target configuration,
patches, selected module sources, shared build rules, tool identities and
relevant make flags). Changed inputs reserve the next unused build number
`CONFIG_OPENWRT_KERNEL_SEQUENCE`; unchanged inputs reuse the recorded number and
kernel build timestamp. Plain `make` targets never reserve a build number. Do not
run a plain full `make` with a number that is already published: the kmod
configuration packages would collide with published identities.

How the kernel packages are assembled:

1. The pack hook (`scripts/kernel-package.py`) moves each kmod's module tree, the
   kernel image and the header tree into
   `build_dir/…/linux-x86_64/kernel-bundle/<release>/`. The `kmod-*` packages
   keep only their configuration files.
2. After all packages are compiled, `package/kernel-bundle`
   (`scripts/kernel-bundle.py`) builds and signs the packages above into the
   target package directory. It refuses a selected kmod that was not packed for
   this release and conflicting module files. It also refuses changed bytes
   under an existing name and version, which require a new build number.
3. The rootfs installs `linux-image-openwrt`, so the image contains
   `linux-image-<release>` from the same build as its `/boot/vmlinuz`.

Publication splits the build into two repositories:

- **Userspace** is published as an immutable snapshot behind `public/current/`.
  It includes the `kmod-*` configuration packages. For legacy routers, the
  snapshot is also reachable through the `public/abi/<config ABI>/` alias.
- The **kernel channel** `public/kernel-upgrades/` holds `linux-image-*`,
  `linux-headers-*`, the metapackages, the virtual `kernel` package and the
  support packages. It keeps the three newest kernel builds. Legacy
  per-generation payloads age out by build number. Routers keep only their
  default and fallback kernels.

Production publication still requires the router preflight described in
[APK upgrade preflight](apk-upgrade-preflight.md). The preflight simulates the
router's real `apk upgrade` against the prepared snapshots before either alias
moves.

## Using it on the router

```sh
apk update
apk upgrade          # installs linux-image-<new> next to the running kernel
kernelctl list       # running / default / fallback / known-good / rescue / counting
reboot               # when convenient
```

`apk upgrade` prints the usual package changes. During the transaction, the APK
hook runs `kernelctl apk-post`, which does the following for each new kernel package:

1. runs `depmod -a <release>`;
2. builds `/boot/kernels/<release>/initramfs.gz`, a small bootstrap with the
   kernel's early-boot modules (from the kmod packages' standard
   `/etc/modules-boot.d` rules) and their firmware;
3. writes GRUB entries for every installed kernel, newest first, each with
   systemd, procd and failsafe variants;
4. makes the newest kernel the default and arms the boot counter.

Nothing changes for the running system until you reboot. `needrestart` and
LuCI's Restart Needed page report `reboot-pending` while a newer default kernel
is installed but not running.

### Boot counting and automatic fallback

A newly installed default kernel gets three boot attempts:

- GRUB decrements `boot_left` in `grubenv` each time it starts the new default.
  When the count is exhausted, it boots `fallback_entry`, which is the previous
  known-good kernel.
- Early in boot, `kernelctl prepare` arms a runtime drop-in for the counted
  kernel only: `FailureAction=reboot` and a 15-minute job timeout on
  `openwrt-kernel-boot.service`.
- `openwrt-kernel-boot.service` (before `boot-complete.target`) runs
  `kernelctl boot`. On the counted kernel, it waits up to 180 s for the
  known-good static local interfaces and LAN addresses, the persistent overlay,
  the OpenWrt service units and SSH. If they come up, the kernel is *blessed*:
  the counter is cleared and the kernel becomes `known_good`. If not, the unit
  fails and the drop-in reboots, so GRUB uses the next attempt.
- WAN, PPPoE or VPN outages never count against a kernel. Only statically
  configured local interfaces are checked, as with
  `openwrt-network-wait-online`.
- A bootstrap (initramfs) failure reboots after 10 seconds through sysrq. A
  kernel panic reboots after 1 s (`CONFIG_PANIC_TIMEOUT=1`, `CONFIG_PANIC_ON_OOPS=y`).
- After the fallback boots, `kernelctl boot` marks the new kernel
  `failed boot`, makes the fallback the default again and clears the counter.

A hard hang without a reboot still needs a reset or a hardware watchdog. A
kernel chosen by hand from the GRUB menu is never counted as a failure.

### Commands

```sh
kernelctl list                     # installed kernels and their roles
kernelctl status                   # full state (JSON)
kernelctl set-default <release>    # like grubby --set-default; not counted
kernelctl rollback                 # make the previous kernel the default again
kernelctl remove <release>         # uninstall a kernel (not running/default/fallback/rescue)
kernelctl check                    # verify boot files and the rescue kernel
```

`apk del linux-image-<release>` is refused; use `kernelctl remove`, which
releases the retention pin and removes the package with APK.

## Retention

Installed kernels are listed in `/etc/openwrt-kernel/protected`. APK adds these
entries to every solve as transaction-only constraints (the `kernel_retain`
policy of the APK patches), so an upgrade never removes the running or previous
kernel. This is the counterpart of Debian's `NeverAutoRemove` or DNF's
installonly protection.

`kernelctl` keeps exactly one active or pending kernel (the default), one
fallback and the legacy rescue kernel. The running kernel is also kept while it
differs from the default, because it cannot be removed. When a new kernel is
installed, it becomes the pending default and the current kernel becomes the
fallback. The previous fallback is withdrawn immediately.
`openwrt-kernel-prune.service` removes withdrawn kernels with APK and deletes
their `/boot/kernels/<release>` directories. A kernel that failed its boots is
pruned once it is no longer the fallback.

## Migration from per-generation kernels

Routers adopted with the previous model (`state.json` schema 1, kernels such as
`…-owrt-<hash>-r1-g45`, per-module payloads `kmod-x-<generation>`) migrate in
two steps. The installed kernelctl of that model cannot validate a kernel
package, so it must be replaced first.

1. **Support packages, no kernel change**:

   ```sh
   apk update
   apk upgrade --userspace-only
   ```

   This installs the new `openwrt-kernel-upgrade` (kernelctl), `lan-apk-feeds`
   and `openwrt-needrestart` while the kernel and kmods stay pinned. The feed
   list then follows `current/` and the kernel channel. kernelctl converts its
   state to schema 2 on first use: the running generation becomes the default
   and known-good kernel, the previous one the fallback, and the original
   kernel stays rescue. A full `apk upgrade` attempted before this step is
   refused by the old kernelctl before any package is written.

2. **First kernel package**:

   ```sh
   apk upgrade
   reboot
   ```

   The `kmod-*` packages become configuration packages and the first
   `linux-image-<release>` is installed as the counted default, with the
   previous generation as fallback. Legacy generations keep their frozen
   firmware and per-generation autoload rules while they boot. Their payload
   packages (`linux-image-…-gN`, `kmod-*-…-gN`, `kernel-dev-headers-…-gN`) are
   pruned as soon as they are neither the default nor the fallback. The
   publication preflight validates step 1 for routers still on schema 1
   (`migration_step: userspace-only` in the receipt).

## Adoption of a fresh image

On the first boot of an image built with kernel packages, `kernelctl boot`
adopts the system after router services are healthy:

- it records the running kernel package as the rescue, default and known-good kernel;
- it snapshots `grub.cfg` to `grub.cfg.rescue` and installs the GRUB dispatcher
  and loadenv modules;
- it writes the retention list;
- it replaces the image's exact `kernel=` world pin with `kernel` and adds
  `linux-image-openwrt`.

Adoption is resumable after its state is saved. APK refuses live installs of
kernel packages until adoption is complete; offline image assembly is allowed.

## Recovery

- In the GRUB menu, choose another installed kernel, or the original kernel
  (rescue, procd recovery or failsafe).
- From a running system, use `kernelctl set-default <release>` or `kernelctl rollback`.
- The rescue entries are parsed before any mutable file. If
  `/boot/grub/openwrt.cfg` is missing or broken, the rescue entries still boot.

Rollback covers the kernel and its modules. Userspace, UCI configuration,
services, VM definitions and data are shared. Keep independent backups and
validate userspace changes separately.

## Scope and verification

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/tests/test-kernel-bundle.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/tests/test-kernel-upgrade.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/tests/test-build-and-publish.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/tests/test-apk-upgrade-preflight.py
KERNEL_POLICY_APK=/path/to/native/patched/apk \
  python3 scripts/tests/test-kernel-apk-policy.py
```

The serial QEMU controller `scripts/tests/kernel-upgrade/vm-console.py` uses
qcow2 overlays, an independent NVMe extroot and isolated user networking. VM
proof is not physical-router proof.

The previous per-generation design and its validation history are kept in
[the validation report](kernel-upgrade-validation.md) and
[the physical deployment report](kernel-upgrade-physical-20261015.md).
