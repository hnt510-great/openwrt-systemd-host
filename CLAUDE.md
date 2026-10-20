# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this tree is

A personal OpenWrt fork tracking `openwrt/openwrt` `main`, currently **94 commits ahead** of
origin, carrying a large amount of local work. It is not vanilla OpenWrt: it is an x86_64
"desktop/virtualization" firmware built on an unusual base combination that everything else
depends on:

- **glibc**, not musl (`CONFIG_LIBC_USE_GLIBC=y`, `CONFIG_USE_GLIBC=y`)
- **APK**, not opkg (`CONFIG_USE_APK=y`), signed packages (`CONFIG_SIGNED_PACKAGES=y`)
- **native systemd** as PID 1 alongside a retained procd (`CONFIG_OPENWRT_SYSTEMD=y`)
- target `x86/64`, kernel 6.18

The fork modifies upstream core files directly — `include/kernel.mk`, `include/package-pack.mk`,
`include/package.mk`, `include/rootfs.mk`, `package/base-files`, `package/system/{apk,procd}`,
`target/linux/x86/image` — so a change you make in `package/custom/` may interact with
build-system surgery described below. Read `docs/` (50 files) before non-trivial work; nearly
every subsystem has a design doc plus a validation record.

## Build commands

```bash
./scripts/feeds update -a          # fetch feeds
./scripts/feeds install -a         # link feed packages into package/feeds/
make defconfig                     # normalize .config after edits
make prereq                        # host build prerequisites
make download                      # prefetch sources into dl/

make V=s                           # full build, verbose (V=99 for debug)
make package/<name>/compile V=s    # one package, e.g. make package/custom/... or package/fastfetch/compile
make target/linux/compile V=s      # kernel only
make package/<name>/prepare|configure|install V=s

make clean                         # artifacts; dirclean/distclean only when intended
```

Fork-specific entrypoints:

```bash
./scripts/build-and-publish.sh -j16          # full make + publish LAN APKs and a kernel generation
./scripts/publish-changed-feeds.sh           # republish only APKs changed by the last build
```

Native (systemd) firmware and its APK repositories land in **`bin/systemd`**; stock images stay
in `bin/targets`. Native and stock builds use separate root staging dirs and rootfs caches while
sharing the toolchain and `dl/`.

## Configuration model

`configs/` holds two different things:

- **Full snapshot** — `configs/x86-64-systemd-desktop.config` (360 KB) is the accepted build
  config. Reproduce it with `cp configs/x86-64-systemd-desktop.config .config && make defconfig`.
  `scripts/diffconfig.sh` does *not* reliably minimize this tree (known Kconfig dependency cycles
  around `video-support`/`openwrt-desktop`/`glib2-gir`/Mesa), so the snapshot is stored in full.
- **Fragments** — `configs/<feature>.config` are kconfig fragments merged by hand, not by any
  script:
  `./scripts/kconfig.pl + .config configs/<feature>.config > .config.new && mv .config.new .config && make defconfig`

`configs/*-feeds.json` are not configs: they are **feed patch-baseline manifests** (`base`,
`commit`, `patch`) for each feature. `configs/lan-apk-feeds.json` is the one file read by a
script — it holds the publisher's `base_url` and `destination`.

## Architecture

### Dual-init: systemd on top of OpenWrt init

`/sbin/init` still mounts early filesystems, runs preinit and mounts the overlay. A GRUB entry
then passes `openwrt.init=systemd`, and init execs systemd as PID 1, falling back to procd if a
preflight check fails; a `procd recovery` entry passes `openwrt.init=procd`. A command line
without a selector defaults to procd.

Systemd owns the manager, units, timers, sockets and journald. The bridge lives in
`package/system/systemd-openwrt/`: `openwrt-ubusd.service` (ubusd), `openwrt-procd.service`
(procd as service supervisor, hotplug and watchdog), `openwrt-services.service` (runs enabled
`/etc/init.d/*` rc scripts in order). UCI, LuCI and rc scripts keep addressing procd-managed
services, so most router-side work is still procd-shaped. See `docs/systemd.md`.

Enabling systemd also switches payloads to a merged `/usr` layout: `scripts/merge-usr.py` runs
from `include/package-pack.mk` and `include/rootfs.mk` per package and on the rootfs, rewriting
`/bin`,`/sbin`,`/lib` to `/usr/...`. It deliberately does not follow image symlinks, and its
`ALTERNATIVE_COMMANDS` set (`dmesg`, `mount`, `passwd`, `ping`, `reboot`, …) marks BusyBox
applets that otherwise collide with standalone tools after the merge. `scripts/tests/test-merge-usr.py`
covers it.

### Feed modification model

`feeds/packages` and `feeds/video` are **separate git repositories** that this fork commits to.
The main repo ignores `feeds/`. To keep those changes reviewable and restorable, they are
mirrored as patch series:

- `patches/feeds/NNNN-<feed>-<topic>.patch` — e.g. `0001-packages-local-integration.patch`
- `configs/*-feeds.json` — records each feed's upstream `base` and local `commit`

On a clean checkout with a matching baseline:
`git -C feeds/packages am "$PWD/patches/feeds/0001-packages-local-integration.patch"`, then
`./scripts/feeds install -a`. **Do not re-apply a patch when the feed working tree already
contains those commits**, and never reset a feed over local commits — a differing upstream
baseline needs review, not overwrite. See `docs/local-build.md`.

### `package/custom/` layout

Wired in as a local feed by the last line of `feeds.conf.default`:
`src-link custom ../package/custom` (~195 tracked files). Recurring patterns:

- **Prebuilt binary repack** — `cmake-bin`, `node-bin`, `firefox-esr-bin` download upstream
  x86_64 tarballs, set `PKGARCH:=x86_64`, leave `Build/Compile` empty, and gate on
  `@TARGET_x86_64 @USE_GLIBC`. `firefox-esr-bin` sets `STRIP:=:`/`RSTRIP:=:` to preserve bundled
  libraries. `package/custom/scripts/update-prebuilt-packages.sh --check|--update` and
  `update-firefox-esr.sh` bump these by hand (SHA-256 verified); nothing runs them automatically.
- **glibc distro compatibility** — `glibc-distro-compat` repackages extra glibc runtime modules
  and `-dev`-style unversioned linker names from `$(TOOLCHAIN_DIR)`, and creates the Debian
  multiarch dirs `/lib/x86_64-linux-gnu` and `/usr/lib/x86_64-linux-gnu` that generic distribution
  binaries expect. `glibc-getent` provides `getent` for NSS lookups (used by distrobox).
- **On-device native development** — `native-libs-dev` repackages target headers, linker names
  and `.pc` files into `/usr`, rewriting staging paths and hand-generating pkg-config files for
  OpenWrt-only libraries; `kernel-dev-headers` repackages the prepared kernel tree plus
  `Module.symvers` and `/lib/modules/.../{build,source}`. Both depend on `+gcc +make +pkgconf` so
  you compile **on the device** with the target toolchain. See `docs/native-development.md`
  (Chinese) and `docs/native-build-tools-validation.md`.
- **Meta-packages** — `openwrt-desktop`, `openwrt-full-utils`, `openwrt-podman-rootless`,
  `openwrt-flatpak` are mostly `DEPENDS` with an empty `Build/Compile`, plus a `files/` payload
  when runtime behavior is needed (init scripts, hotplug rules, PAM config, udev rules).
  `openwrt-full-utils` also uses `ALTERNATIVES:=` to prefer standalone tools (`vim`, `netstat`)
  over BusyBox applets with recovery fallbacks.
- **Shared X.Org includes** — `xorg-client.mk` (autotools) and `xorg-meson.mk` (meson) define
  `Package/$(PKG_NAME)`, `Build/InstallDev` and install rules; leaf Makefiles set only
  `PKG_NAME`, source, and `XORG_DEPENDS`. Both add
  `PKG_FILE_DEPENDS+=$(CURDIR)/../<fragment>.mk` so editing the fragment invalidates every
  dependent package.

### Kernel generations and upgrades

`package/custom/openwrt-kernel-upgrade` implements parallel ABI-pinned kernels with protected
GRUB recovery. The engine is `files/kernelctl` (Python 3), driven by `kernelctl prepare` at
startup (`kernel-generation.init`, `START=09`) and `kernelctl boot` via
`openwrt-kernel-boot.service`; state lives in `/etc/openwrt-kernel/`. `files/init` is a minimal
bootstrap that mounts dev/proc/sys, resolves `root=` (PARTUUID) and `switch_root`s — it is *not*
OpenWrt's standalone initramfs. Host-side, `scripts/kernel-build-inputs.py` fingerprints the
build inputs, `scripts/publish-kernel-upgrade-feed.py` publishes a generation, and the
`CONFIG_OPENWRT_KERNEL_UPGRADE` / `CONFIG_OPENWRT_KERNEL_SEQUENCE` gates are in
`config/Config-build.in`. The `openwrt-kernel-policy` dependency is a `PROVIDES` from
`package/system/apk`, not a package directory. Docs: `docs/kernel-upgrade.md`.

### LAN APK feed publishing

Host side (`scripts/`, not a package): `publish-lan-apk-feeds.py` publishes ABI-matched
repositories under `configs/lan-apk-feeds.json`'s `destination` (`/srv/openwrt-feeds`) for its
`base_url`; `serve-lan-apk-feeds.py` serves them; `build-and-publish.py` orchestrates a build
→ userspace publish → kernel generation, importing the three sibling scripts via `importlib`,
locking on `tmp/.build-and-publish.lock`, and tracking generations in
`tmp/.kernel-publication-inputs.json`.

Router side: `package/custom/lan-apk-feeds` is the consumer. `lan-apk-feeds-sync` reads the
installed kernel from `/lib/apk/db/installed` (refined by `/etc/openwrt-kernel/state.json` when
present), then writes an ABI-pinned `/etc/apk/repositories.d/lan-local.list` such as
`<base>/abi/<kernel-abi>/<repo>/packages.adb`. It refuses to overwrite unmanaged files and
stamps `# Managed by lan-apk-feeds-sync.`; an rc init (`START=11`) syncs at boot and an APK
commit hook re-syncs after transactions. See `docs/lan-apk-feeds.md`.

### Scheduled upstream integration (the tree changes itself)

`scripts/scheduled-maintenance.py` is driven by a marked host cron block, configured by
`configs/scheduled-maintenance.json` (state root `/srv/openwrt-automation`, 8 jobs,
two repair attempts). It fires every **72 hours, in this same workspace** — no second checkout is
created. A run:

1. snapshots local inputs to private `refs/automation/*` refs and a private backup dir without
   staging or committing on the user's branches;
2. hands the merge to the user's existing **Codex app-server daemon** over a Unix WebSocket
   (`scripts/codex-daemon-task.py`), which merges `main` and the git feeds **in place**,
   auto-resolving conflicts while preserving local features and user stashes;
3. regens feed indexes, normalizes Kconfig (requiring `conf --fatalrecursive`), and builds the
   full image, allowing up to two Codex repair attempts that may not disable core features;
4. boots the exact image under KVM/UEFI as a **two-VM pair** (router + LAN client on a private
   QEMU socket network) and checks systemd/procd, WAN DHCP, LAN DHCP/default route, DNS,
   routed/NATed client HTTP and authenticated LuCI;
5. only then publishes, reserving a kernel generation through `build-and-publish.py`'s
   `build-only` mode plus the signed publisher.

Practical consequences: the tree can change between sessions, automatic integration commits can
appear next to your uncommitted work, and `.config` may be normalized. The lock prevents
overlapping *scheduled* runs but does **not** lock out your editor or a manual build. Check
before starting anything long, and note that a failed merge is left intact with **no automatic
rollback** — resolve the unfinished Git operation before the next slot:

```bash
python3 scripts/scheduled-maintenance.py --status
python3 scripts/scheduled-maintenance.py --run-now
```

The VM checks cover virtual Ethernet, DHCP/DNS, routing/NAT and LuCI only — they prove nothing
about physical NIC, PPPoE, Wi-Fi or hardware acceleration. To re-run just the image test against
an image, without publishing:

```bash
python3 scripts/test-image-network.py --image bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz --work-dir <new empty dir>
```

See `docs/scheduled-maintenance.md` and `docs/upstream-merge-20261016.md` (a worked merge record).

## Testing

There is no single repository-wide test command. Run the narrowest relevant check:

```bash
python3 scripts/tests/test-<topic>.py        # unittest-style host tests
node scripts/tests/test-<app>-view.js        # LuCI view logic
sh scripts/tests/test-alternatives.sh        # alternative/symlink handling
sh scripts/test-<feature>.sh                 # appimage, distrobox, full-utils, native-libs,
                                             # native-build-tools, podman-rootless
python3 scripts/tests/test-scheduled-maintenance.py   # scheduler cadence, locking, state
python3 scripts/tests/test-build-and-publish.py       # build/publication orchestration
```

Some checks must run **on the target or a guest VM** after flashing or booting an image:
`scripts/tests/*-guest-smoke.sh` (systemd, journald, libvirt, virt-manager),
`scripts/tests/firefox-smoke.sh`, `scripts/tests/desktop-kernel-smoke.py`,
`scripts/tests/kernel-upgrade/vm-console.py`, and the C probes
(`appimage-probe.c`, `virtio-egl-probe.c`, `spice-gl-reset.py`). For package builds prefer
`make package/<name>/compile V=s`; use `scripts/deptest.sh <package>` for dependency checks;
`scripts/checkpatch.pl` for C and kernel-adjacent patches.

## Documentation and commit conventions

Every feature is documented as a pair: a guide `docs/<topic>.md` and a validation record
`docs/<topic>-validation.md` (22 validation files). Guides give setup commands, UCI option
tables and recovery steps, and link to their validation doc. Validation records are
**hand-written, not generated**, and contain the image path and SHA256, a `| Check | Result |`
table, and an explicit scope statement (often "no physical device was flashed") plus an
**Evidence** pointer to a dated workspace kept *outside* the repo, e.g.
`/srv/openwrt-validation/kernel-upgrade-validation-20261015/`. Dated run reports also appear as
standalone files (`docs/kernel-upgrade-physical-20261015.md`). Some older docs are in Chinese
(`docs/local-build.md`, `docs/native-development.md`); newer ones are English — match the
neighbouring document.

### Other agent-facing files

- `AGENTS.md` (locally added in `eb802fe873`) is a generic OpenWrt template that overlaps this
  file and omits the systemd/APK/glibc specifics — prefer this file where they disagree.
- `README.md` is unmodified upstream text; its "installed via the OpenWrt package manager called
  `opkg`" claim does not describe this tree, which uses APK.
- `.github/llm-review-rules.md` holds project-specific review rules. The practically useful part:
  OpenWrt patches are quilt-managed, so regenerate a patch with `make target/linux/refresh` (or
  `make package/<pkg>/refresh`, e.g. `make package/mac80211/refresh`) — never `git format-patch`.
- Native-systemd images ship an on-device discovery guide, `package/base-files/system-description.systemd.md`,
  pointed at by `OPENWRT_SYSTEM_DESCRIPTION_FILE`; it records image-selected capabilities, not
  live service state. The same commit gives `/etc/os-release` `ID=openwrt-systemd`,
  `VARIANT_ID=native-systemd` while `/etc/openwrt_release` keeps OpenWrt-compatible fields.

Commit subjects use `area: imperative summary` (e.g. `systemd: maintain full kmod indexes
through boot and APK changes`, `realtek: dsa: tc: offload flower rules of chain 0 only`).
Feature commits typically add the code, the config fragment or snapshot update, and both docs
together. Before pulling upstream, a `backup/pre-upstream-<date>` branch is cut; existing
examples include `backup/pre-upstream-20261016T023630`.

## Gotchas

- **Host automation mutates this workspace.** A 72-hour cron run merges upstream in place, may
  normalize `.config`, and advances `tmp/.kernel-publication-inputs.json`; on failure it leaves an
  unfinished merge behind with no rollback (see *Scheduled upstream integration* above). Run the
  status command before a long build, and don't hand-edit `tmp/` state files.
- `package/luci-theme-argon` and `package/luci-app-argon-config` are **embedded git
  repositories** (gitlinks with no `.gitmodules`). Commits inside them are not recorded by the
  parent repo; treat version selection there as a separate repository operation.
- `feeds/` is git-ignored but *is* source — `feeds/packages` and `feeds/video` hold local
  commits that the main repo only records as patches and JSON manifests.
- Untracked clutter that is not source: `.DS_Store`/`._.DS_Store`,
  `backup-OpenWrt-2026-08-30.tar.gz`, `scripts/__pycache__/`,
  `package/custom/openwrt-kernel-upgrade/files/__pycache__/`, `package/fastfetch/.claude/`.
- `files/` is the rootfs overlay, and `.gitignore` ignores the whole directory (`/files`).
  Exactly **11 files were force-added** and are versioned: `etc/config/fstab`, `etc/skel/.zshrc`,
  `etc/ssh/sshd_config.d/00-openwrt-access.conf`, `etc/sudoers.d/10-multiuser`,
  `etc/uci-defaults/{99-multiuser,99-openssh-access,99-uhttpd-luci,99-zsh-default}`,
  `etc/zsh/zshrc`, `lib/upgrade/keep.d/{multiuser,openssh-access}`. Everything else under `files/` — including
  `etc/uci-defaults/99-local-user` (which carries a personal account password hash) and the
  personal network/DDNS/proxy configs — is present on disk but **unversioned**. Do not assume a
  file under `files/` is tracked, and do not commit those personal files. `docs/multiuser.md`
  and `docs/multiuser.md` describe the intended account state.
- The fork's images and packages are published, not deployed: `build-and-publish.sh` and
  `publish-changed-feeds.sh` write to `configs/lan-apk-feeds.json`'s destination and never push
  to a router.

## External documentation

- OpenWrt Developer Guide: https://openwrt.org/docs/guide-developer/start
- Build System Setup: https://openwrt.org/docs/guide-developer/build-system/install-buildsystem
- Upstream repository: https://github.com/openwrt/openwrt.git
