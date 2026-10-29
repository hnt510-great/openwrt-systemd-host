# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this tree is

A personal OpenWrt fork tracking `openwrt/openwrt` `main`, roughly **180 commits ahead** of origin
and still growing. It is not vanilla OpenWrt: it is an x86_64 "router plus desktop" firmware built
on an unusual base combination that everything else depends on:

- **glibc**, not musl (`CONFIG_LIBC_USE_GLIBC=y`, `CONFIG_USE_GLIBC=y`)
- **APK**, not opkg (`CONFIG_USE_APK=y`), signed packages (`CONFIG_SIGNED_PACKAGES=y`)
- **native systemd** as PID 1 alongside a retained procd (`CONFIG_OPENWRT_SYSTEMD=y`)
- target `x86/64`, now on **mainline Linux 7.3** (`CONFIG_LINUX_7_3=y`); the versioned 6.18
  configuration and patch directories are retained, and other subtargets/boards keep their own
  kernel selection
- a shared-user **GNOME desktop** session (local display, LAN RDP, Sunshine/Moonlight) replacing
  the earlier Weston profile

The fork modifies upstream core files directly — `include/kernel.mk`, `include/package-pack.mk`,
`include/package.mk`, `include/rootfs.mk`, `package/base-files`, `package/system/{apk,procd,systemd}`,
`target/linux/x86/image` — so a change in `package/custom/` may interact with build-system surgery
described below. Read `docs/` (87 files, 41 hand-written validation records at last count) before
non-trivial work; nearly every subsystem has a design doc plus a validation record.

## Build commands

```bash
./scripts/feeds update -a          # fetch feeds AND bump registered custom recipe versions
./scripts/feeds install -a         # link feed packages into package/feeds/
make defconfig                     # normalize .config after edits
make prereq                        # host build prerequisites
make download                      # prefetch sources into dl/

make V=s                           # full build, verbose (V=99 for debug)
make package/<name>/compile V=s    # one package, e.g. package/custom/... or package/fastfetch/compile
make target/linux/compile V=s      # kernel only
make package/<name>/prepare|configure|install V=s
make target/linux/refresh          # regenerate quilt patches (or make package/<pkg>/refresh)
```

`./scripts/feeds update` is not a plain fetch here: after the other selected feeds succeed it runs
`scripts/update-custom-packages.py --update`, which queries upstream versions for every recipe
registered in `configs/custom-package-updates.json` and edits those recipes. Inspect local changes
before running it, and use `./scripts/feeds update -i -a` when you only want indexes. A new custom
package **must** be registered in that JSON or the updater fails.

Fork-specific entrypoints:

```bash
./scripts/build-and-publish.sh -j16            # make + publish userspace APKs and a kernel generation
./scripts/publish-changed-feeds.sh [--dry-run] # full publication preflight, then publish changed APKs
python3 scripts/build-and-publish.py build-only -j12 V=s  # reserve a generation, build, do not publish
python3 scripts/update-mainline-kernel.py --check|--update
```

Native (systemd) firmware and its APK repositories land in **`bin/systemd`**; stock images stay in
`bin/targets`. Native and stock builds use separate root staging dirs and rootfs caches while
sharing the toolchain and `dl/`.

## Configuration model

`configs/` holds two different things:

- **Full snapshot** — `configs/x86-64-systemd-desktop.config` (356 KB) is the last accepted build
  config. Reproduce it with `cp configs/x86-64-systemd-desktop.config .config && make defconfig`.
  `scripts/diffconfig.sh` does *not* reliably minimize this tree (known Kconfig dependency cycles
  around `video-support`/`openwrt-desktop`/`glib2-gir`/Mesa), so the snapshot is stored in full.
- **Fragments** — `configs/<feature>.config` are kconfig fragments merged by hand, not by any
  script:
  `./scripts/kconfig.pl + .config configs/<feature>.config > .config.new && mv .config.new .config && make defconfig`

The snapshot still describes the **Weston** desktop. The current target is GNOME, selected by
merging `configs/gnome-desktop.config`, which explicitly disables `weston`, `seatd`,
`libudev-zero` and `openwrt-desktop-launcher` and selects `gnome-shell`, `gnome-remote-desktop`,
`sunshine`, Flatpak/AppImage and the IME/audio meta-packages. Do not assume the snapshot alone
reproduces the current desktop profile.

`configs/*-feeds.json` are **feed patch-baseline manifests** (`base`, `commit`, `patch`) for each
feature, not configs. `configs/lan-apk-feeds.json` is the one every publisher reads: it holds
`base_url`, `destination` and `upgrade_preflight.ssh_target`.

## Architecture

### Dual-init: systemd on top of OpenWrt init

`/sbin/init` still mounts early filesystems, runs preinit and mounts the overlay. A GRUB entry then
passes `openwrt.init=systemd`, and init execs systemd as PID 1, falling back to procd if a preflight
check fails; a `procd recovery` entry passes `openwrt.init=procd`. A command line without a selector
defaults to procd.

Systemd owns the manager, units, timers, sockets and journald. The bridge lives in
`package/system/systemd-openwrt/`: `openwrt-ubusd.service` (ubusd), `openwrt-procd.service` (procd
as service supervisor, hotplug and watchdog), `openwrt-services.service` (runs enabled
`/etc/init.d/*` rc scripts in order). UCI, LuCI and rc scripts keep addressing procd-managed
services, so most router-side work is still procd-shaped. See `docs/systemd.md`.

An optional compatibility bridge (`CONFIG_OPENWRT_SYSTEMD_SERVICE_BRIDGE`, off by default,
`package/system/systemd-openwrt-services/`) adds a C daemon that maps
`systemctl start|stop|restart|reload|enable openwrt@NAME.service` onto the original init scripts.
It does not convert daemons to native supervision and generates no units; `dbus` and `sshd` are
excluded because they have native units. See `docs/systemd-service-bridge.md` and
`docs/systemd-cgroups.md` (scopes/slices, logind, delegation).

Enabling systemd also switches payloads to a merged `/usr` layout: `scripts/merge-usr.py` runs
from `include/package-pack.mk` and `include/rootfs.mk` per package and on the rootfs, rewriting
`/bin`,`/sbin`,`/lib` to `/usr/...`. It deliberately does not follow image symlinks, and its
`ALTERNATIVE_COMMANDS` set (`dmesg`, `mount`, `passwd`, `ping`, `reboot`, …) marks BusyBox
applets that otherwise collide with standalone tools after the merge. `scripts/tests/test-merge-usr.py`
covers it.

### GNOME desktop profile

`package/custom/openwrt-desktop` is the meta-package: an ordinary user's GNOME 51 session on VT7,
started through PAM/logind, sharing the local display over `gnome-remote-desktop` (RDP, LAN IPv4
only) and Sunshine. There is no Weston, no seatd and no separate RDP login session. Companion
meta-packages are `openwrt-desktop-ime` (Fcitx5 with the GNOME Kimpanel extension) and
`openwrt-desktop-audio` (PipeWire/PulseAudio adapter).

Provisioning is on-device and root-only:

```sh
desktop-setup USER
desktop-rdp-setup USER [--password-stdin]
sunshine-setup USER --capture=portal|--enable-kms
desktop-audio-setup USER        # RDP-only setups
```

Keyring unlock uses a root-only bootstrap secret under `/etc/desktop/gnome/` passed through
systemd `LoadCredential`; never put user passwords or credentials in firmware or image overlays.
The recipes cover session startup through PAM/logind (no display manager),
GTK4/GJS/SpiderMonkey, Xwayland, XDG portals, `systemd-udev`/logind seats, and the pinned Kimpanel
extension. See `docs/gnome-desktop.md`;
`docs/desktop.md` documents the superseded Weston/VNC profile.

### Kernel: mainline series and parallel generations

**Series management.** `target/linux/x86/64` selects Linux 7.3; `scripts/update-mainline-kernel.py
--check|--update` compares numeric versions against kernel.org, verifies the source archive SHA-256,
applies the generic backport/pending/hack and x86 stacks with zero fuzz into an isolated directory,
and only then rewrites version/hash metadata. `--update` handles point releases within the ported
series; an unported series reports `port-required` rather than pretending support. Exit status 0 is
current/updated, 1 is an update available in check mode, 2 is a required new-series port or error.
Patch disposition for the 6.18→7.3 migration is recorded in
`configs/mainline-kernel-patches.json`; findings for optional configurations are in
`docs/mainline-kernel-patch-review.md`. This is independent of feeds and scheduled maintenance.

**Generations.** `package/custom/openwrt-kernel-upgrade` implements parallel ABI-pinned kernels with
protected GRUB recovery. The engine is `files/kernelctl` (Python 3), driven by `kernelctl prepare`
at startup (`kernel-generation.init`, `START=09`) and `kernelctl boot` via
`openwrt-kernel-boot.service`. State lives in `/etc/openwrt-kernel/`. `files/init` is a minimal
bootstrap that mounts dev/proc/sys, resolves `root=` (PARTUUID) and `switch_root`s — it is *not*
OpenWrt's standalone initramfs. Host-side, `scripts/kernel-build-inputs.py` fingerprints the build
inputs, `scripts/publish-kernel-upgrade-feed.py` publishes a generation, and the
`CONFIG_OPENWRT_KERNEL_UPGRADE` / `CONFIG_OPENWRT_KERNEL_SEQUENCE` gates are in
`config/Config-build.in`. The `openwrt-kernel-policy` dependency is a `PROVIDES` from
`package/system/apk`, not a package directory. Generations are reserved and timestamped by
`build-and-publish.py`; plain `make` targets do not reserve one, and a new image must never be mixed
with modules or headers from the previous ABI. See `docs/kernel-upgrade.md`.

### ELF ABI and signed APK packaging

Packages declare real shared-library contracts instead of only build-time deps.
`scripts/elf-abi.py` reads ELF headers/strings directly (no target loader) and each native payload
gets `/usr/lib/apk/packages/<name>.elf.json`; public libraries provide `so:<SONAME>=0`, private
libraries satisfy only matching loader paths, and provider `pkginfo/<name>.sonames` stamps rebuild
consumers when capabilities change. `configs/elf-abi-policy.json` records explicit bootstrap
loader paths (Firefox, Samba modules). Ucode's interpreter/module ABI lock is separate
(`scripts/ucode-abi.py`) because SONAME cannot describe it.

`configs/apk-elf-rebuilds.mk` is a version ledger for one-time metadata migrations: it maps exact
input versions to new effective releases without editing hundreds of feed recipes, and entries
expire when the source version changes. `scripts/migrate-elf-abi.py` repackages compatible signed
APKs in fakeroot (verifying every other file), while `scripts/apply-elf-migration.py` is the
target-side installer with backups and a 20-minute systemd rollback timer. Published package
identities are immutable: changed bytes require a new `PKG_RELEASE`. The publisher independently
re-extracts and scans every newest candidate, including retained incremental packages, and rejects
missing/stale inventories or unresolved libraries. See `docs/elf-abi-upgrades.md`.

### APK upgrade preflight and publication gate

`scripts/apk-upgrade-preflight.py` (with patched APK ≥ 3.0.5-r13) makes publication depend on the
*installed* router being able to upgrade, not just on a self-consistent build. APK supports
`--plan-json FILE` (mode 0600 report of mode, status, blockers, inputs, indexes, kernel ABI and
changes) and `--userspace-only`, which pins ABI-bound kernel packages by identity in a private
solver world. Managed transactions cache and verify payloads before writing. `configs/apk-migrations.json`
is the schema-1 registry for explicit empty-package migrations (currently kernel packages only).

`scripts/publish-changed-feeds.sh` is the production path; it takes a destination-wide lock,
prepares signed userspace and kernel snapshots, reads a consistent router baseline under APK's
database lock, checks installed kmods against the candidate ABI, simulates both upgrade paths,
rechecks hashes, then exposes userspace before the kernel pointer. Receipts are written under
`<destination>/upgrade-receipts/`. Production publication **requires**
`upgrade_preflight.ssh_target` (`configs/lan-apk-feeds.json`, currently `desktop-user@192.0.2.1`); an
unreachable router or pending kernel trial stops publication, and direct low-level production
publication is rejected. `--dry-run` performs the full preflight and discards the snapshots.
Publication never installs on the physical router. See `docs/apk-upgrade-preflight.md`.

### Feed modification model

`feeds/packages` and `feeds/video` are **separate git repositories** that this fork commits to.
The main repo ignores `feeds/`. To keep those changes reviewable and restorable, they are mirrored
as patch series:

- `patches/feeds/NNNN-<feed>-<topic>.patch` — e.g. `0001-packages-local-integration.patch`
- `configs/*-feeds.json` — records each feed's upstream `base` and local `commit`
  (`configs/local-feeds.json` covers the main `packages`/`video` integration)

On a clean checkout with a matching baseline:
`git -C feeds/packages am "$PWD/patches/feeds/0001-packages-local-integration.patch"`, then
`./scripts/feeds install -a`. **Do not re-apply a patch when the feed working tree already contains
those commits**, and never reset a feed over local commits — a differing upstream baseline needs
review, not overwrite. See `docs/local-build.md` (Chinese).

### `package/custom/` layout

Wired in as a local feed by the last line of `feeds.conf.default`:
`src-link custom ../package/custom` (~370 tracked files). Recurring patterns:

- **Prebuilt binary repack** — `cmake-bin`, `node-bin`, `firefox-esr-bin` download upstream x86_64
  tarballs, set `PKGARCH:=x86_64`, leave `Build/Compile` empty, and gate on
  `@TARGET_x86_64 @USE_GLIBC`. `firefox-esr-bin` sets `STRIP:=:`/`RSTRIP:=:` to preserve bundled
  libraries. `package/custom/scripts/update-prebuilt-packages.sh --check|--update` and
  `update-firefox-esr.sh` bump these by hand (SHA-256 verified); nothing runs them automatically.
  Versions are also tracked in `configs/custom-package-updates.json`.
- **glibc distro compatibility** — `glibc-distro-compat` repackages extra glibc runtime modules
  and `-dev`-style unversioned linker names from `$(TOOLCHAIN_DIR)`, and creates the Debian
  multiarch dirs `/lib/x86_64-linux-gnu` and `/usr/lib/x86_64-linux-gnu` that generic distribution
  binaries expect. `glibc-getent` provides `getent` for NSS lookups (used by distrobox);
  `glibc-gconv`/`glibc-locale-utf8` supply conversions and UTF-8 locales.
- **On-device native development** — `native-libs-dev` repackages target headers, linker names
  and `.pc` files into `/usr`, rewriting staging paths and hand-generating pkg-config files for
  OpenWrt-only libraries; `kernel-dev-headers` repackages the prepared kernel tree plus
  `Module.symvers` and `/lib/modules/.../{build,source}`; `native-build-deps` and
  `cockpit-runtime-deps` select the broader build/runtime set. See `docs/native-development.md`
  (Chinese) and `docs/native-build-tools-validation.md`.
- **Desktop and virtualization stack** — GNOME 51, GTK4/libadwaita, GJS/SpiderMonkey, the X
  libraries, Fcitx5, PipeWire, `libvirt`/`virt-manager`/`qemu`, SPICE/FreeRDP, `sunshine`,
  `gnome-remote-desktop`, `needrestart` and its LuCI app. Leaf X recipes share
  `xorg-client.mk` (autotools) and `xorg-meson.mk` (meson), which define `Package/$(PKG_NAME)`,
  `Build/InstallDev` and install rules and add
  `PKG_FILE_DEPENDS+=$(CURDIR)/../<fragment>.mk` so editing the fragment invalidates every
  dependent package.
- **Meta-packages** — `openwrt-desktop`, `openwrt-desktop-ime`, `openwrt-desktop-audio`,
  `openwrt-desktop-launcher`, `openwrt-full-utils`, `openwrt-podman-rootless`,
  `openwrt-flatpak`, `openwrt-appimage`, `openwrt-needrestart` are mostly `DEPENDS` with an empty
  `Build/Compile`, plus a `files/` payload when runtime behavior is needed (init scripts, hotplug
  rules, PAM config, udev rules, setup helpers). `openwrt-full-utils` also uses `ALTERNATIVES:=`
  to prefer standalone tools (`vim`, `netstat`) over BusyBox applets with recovery fallbacks.

Every custom recipe is registered in `configs/custom-package-updates.json` with an update mode
(`series`, `major`, `stable`, `follow`, `local`); the updater fails on unregistered, stale or
duplicate entries.

### LAN APK feed publishing and serving

Host side (`scripts/`, not a package): `publish-lan-apk-feeds.py` publishes ABI-matched
repositories under `configs/lan-apk-feeds.json`'s `destination` (`/srv/openwrt-feeds`) for its
`base_url`; nginx serves them as the host system unit `lan-apk-feeds.service`
(`configs/lan-apk-feeds.nginx.conf`); `build-and-publish.py` orchestrates make → userspace publish
→ kernel generation, importing the sibling scripts via `importlib`, locking on
`tmp/.build-and-publish.lock`, and tracking generations in `tmp/.kernel-publication-inputs.json`.
`--incremental` is compatibility-only; publication is always incremental.

Router side: `package/custom/lan-apk-feeds` is the consumer. `lan-apk-feeds-sync` reads the
installed kernel from `/lib/apk/db/installed` (refined by `/etc/openwrt-kernel/state.json` when
present), then writes an ABI-pinned `/etc/apk/repositories.d/lan-local.list` from the
`repositories=` list in `/etc/lan-apk-feeds.conf`, as `<base>/abi/<kernel-abi>/<repo>/packages.adb`
plus the `kernel-upgrades` channel when generation state exists.
It preserves unrelated repositories and refuses to overwrite unmanaged files, stamping
`# Managed by lan-apk-feeds-sync.`; an rc init (`START=11`) syncs at boot and an APK commit hook
re-syncs after transactions. See `docs/lan-apk-feeds.md`.

### Scheduled upstream integration — currently disabled

Automatic maintenance was **disabled at the user's request on 2026-10-18**; the host cron entry was
removed and `scripts/scheduled-maintenance.py --status` reports no schedule. Do not reinstall the
cron job or start the workflow unless the user explicitly asks again. The implementation, logs and
state are retained.

The workflow (documented in `docs/scheduled-maintenance.md`) would run every 72 hours at 04:00
Asia/Singapore in this same workspace, driven by `configs/scheduled-maintenance.json` (state root
`/srv/openwrt-automation`, eight jobs, two repair attempts). It snapshots local inputs
to private `refs/automation/*`, hands merging to the user's Codex app-server daemon over a Unix
WebSocket, normalizes Kconfig (`conf --fatalrecursive`), builds, boots the exact image as a two-VM
router+client pair under KVM/UEFI, and only then publishes. A failed merge is left intact with **no
automatic rollback**. The lock only excludes overlapping scheduled runs, not manual builds. If the
user asks to operate it:

```bash
python3 scripts/scheduled-maintenance.py --status
python3 scripts/scheduled-maintenance.py --run-now
```

The VM gate covers virtual Ethernet, DHCP/DNS, routing/NAT and LuCI only — not physical NIC, PPPoE,
Wi-Fi or hardware acceleration. To re-run just the image test:

```bash
python3 scripts/test-image-network.py --image <exact .img.gz> --work-dir <new empty dir>
```

## Testing

There is no single repository-wide test command. Run the narrowest relevant check:

```bash
python3 scripts/tests/test-<topic>.py        # host tests, e.g. test-elf-abi, test-ucode-abi,
                                             # test-apk-upgrade-preflight, test-lan-apk-publisher,
                                             # test-build-and-publish, test-kernel-upgrade,
                                             # test-mainline-kernel-updates, test-scheduled-maintenance,
                                             # test-systemd-service-bridge, test-merge-usr, test-needrestart
node scripts/tests/test-<app>-view.js        # LuCI view logic
sh scripts/tests/test-alternatives.sh        # alternative/symlink handling
sh scripts/test-<feature>.sh                 # appimage, distrobox, full-utils, native-libs,
                                             # native-build-tools, native-app-deps, podman-rootless
```

Some checks must run **on the target or a guest VM** after flashing or booting an image:
`scripts/tests/*-guest*.sh|py` (systemd, journald, libvirt, virt-manager, GNOME desktop, audio,
input, SSH, cgroups, needrestart), `firefox-smoke.sh`, `desktop-kernel-smoke.py`,
`sunshine-stream-*`, `kernel-upgrade/vm-console.py`, and the C probes (`appimage-probe.c`,
`virtio-egl-probe.c`, `spice-gl-reset.py`, `desktop-seat-retirement.c`). For package builds prefer
`make package/<name>/compile V=s`; use `scripts/deptest.sh <package>` for dependency checks and
`scripts/checkpatch.pl` for C and kernel-adjacent patches. ELF/publication changes should also pass
`git diff --check`.

## Documentation and commit conventions

Every feature is documented as a pair: a guide `docs/<topic>.md` and a validation record
`docs/<topic>-validation.md` (41 validation files). Guides give setup commands, UCI option tables
and recovery steps, and link to their validation doc. Validation records are **hand-written, not
generated**, and contain the image path and SHA256, a `| Check | Result |` table, and an explicit
scope statement (often "no physical device was flashed") plus an **Evidence** pointer to a dated
workspace kept *outside* the repo, e.g. `/srv/openwrt-validation/kernel-upgrade-validation-20261015/`.
Dated run reports also appear as standalone files (e.g. `docs/mainline-kernel-deployment-20261024.md`).
Older docs are Chinese (`docs/local-build.md`, `docs/native-development.md`,
`docs/custom-package-updates.md`); newer ones are English — match the neighbouring document.

Commit subjects use `area: imperative summary` (e.g. `systemd: maintain full kmod indexes through
boot and APK changes`, `desktop: replace Weston with GNOME and native RDP`). Feature commits
typically add the code, the config fragment or snapshot update, and both docs together. Before
pulling upstream, a `backup/pre-upstream-<date>` branch is cut.

### Other agent-facing files

- `AGENTS.md` and `GEMINI.md` are generic OpenWrt/agent summaries that omit or contradict the
  systemd/APK/glibc specifics — prefer this file.
- `README.md` is unmodified upstream text; its "installed via the OpenWrt package manager called
  `opkg`" claim does not describe this tree, which uses APK.
- `.github/llm-review-rules.md` holds project-specific review rules. Beyond patch regeneration, it
  requires LED properties (`color`/`function`, not `label = "green:status"`) and `nvmem-cells` for
  MACs instead of `mediatek,mtd-eeprom`, and requires new-device commits to document hardware,
  flash instructions and MAC layout.

## Gotchas

- **Host automation is off.** Do not reinstall the 72-hour cron block without an explicit user
  request (`docs/scheduled-maintenance.md`). There is no background merge/normalization right now.
- **Publication is gated on the real router.** `publish-changed-feeds.sh` and
  `build-and-publish.sh` fail without a reachable `upgrade_preflight.ssh_target` and a passing
  simulation. There is no offline production publish, and direct low-level production publication
  is rejected. A dry run still performs the full router preflight.
- **`.config` and the snapshot are not the GNOME profile.** Both currently select Weston; GNOME
  requires merging `configs/gnome-desktop.config`. Re-check before claiming a desktop change was
  built.
- **Plain make does not reserve a kernel generation.** Use `build-and-publish.py build-only` or the
  wrappers for full builds; never pair a new image with old-ABI modules or headers.
- **Published APK identities are immutable.** Changed bytes require a new `PKG_RELEASE`; the ELF
  rebuild ledger is not permission to overwrite a released version.
- `package/luci-theme-argon` and `package/luci-app-argon-config` are **embedded git repositories**
  (gitlinks with no `.gitmodules`). Commits inside them are not recorded by the parent repo; treat
  version selection there as a separate repository operation.
- `feeds/` is git-ignored but *is* source — `feeds/packages` and `feeds/video` hold local commits
  that the main repo only records as patches and JSON manifests. Never reset them.
- Untracked clutter that is not source: `.DS_Store`/`._.DS_Store`, backup tarballs,
  `scripts/__pycache__/`, `scripts/tests/__pycache__/`,
  `package/custom/openwrt-kernel-upgrade/files/__pycache__/`, `package/fastfetch/.claude/`,
  `.claude/`. Root `private-key.pem`/`public-key.pem` are signing material and git-ignored.
- `files/` is the rootfs overlay, and `.gitignore` ignores the whole directory (`/files`).
  Exactly **11 files were force-added** and are versioned: `etc/config/fstab`, `etc/skel/.zshrc`,
  `etc/ssh/sshd_config.d/00-openwrt-access.conf`, `etc/sudoers.d/10-multiuser`,
  `etc/uci-defaults/{99-multiuser,99-openssh-access,99-uhttpd-luci,99-zsh-default}`,
  `etc/zsh/zshrc`, `lib/upgrade/keep.d/{multiuser,openssh-access}`. Everything else under `files/` —
  including `etc/uci-defaults/99-local-user` (personal password hash) and personal
  network/DDNS/proxy configs — is present on disk but **unversioned**. Do not commit those.
  `docs/multiuser.md` and `docs/multiuser.md` describe the intended account state.
- OpenWrt patches are quilt-managed: regenerate with `make target/linux/refresh` or
  `make package/<pkg>/refresh`, never `git format-patch`.
- The fork's images and packages are published, not deployed: the wrappers write to
  `configs/lan-apk-feeds.json`'s destination and never push to a router or Git remote.
- Native-systemd images ship `package/base-files/system-description.systemd.md` via
  `OPENWRT_SYSTEM_DESCRIPTION_FILE`; `/etc/os-release` uses `ID=openwrt-systemd`,
  `VARIANT_ID=native-systemd`, while `/etc/openwrt_release` keeps OpenWrt-compatible fields.

## External documentation

- OpenWrt Developer Guide: https://openwrt.org/docs/guide-developer/start
- Build System Setup: https://openwrt.org/docs/guide-developer/build-system/install-buildsystem
- Upstream repository: https://github.com/openwrt/openwrt.git
