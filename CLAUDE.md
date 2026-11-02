# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this tree is

A personal OpenWrt fork tracking `openwrt/openwrt` `main`, roughly **240 commits ahead** of origin
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
- router datapath additions: full cone NAT in kernel/nftables/firewall4, a netlink fast path for
  dnsmasq `nftset`, and opt-in `daed` (eBPF transparent proxy) beside the default Passwall

The fork modifies upstream core files directly — `include/kernel.mk`, `include/package-pack.mk`,
`include/package.mk`, `include/rootfs.mk`, `package/base-files`, `package/system/{apk,procd,systemd}`,
`package/network/{services/dnsmasq,utils/nftables,config/firewall4}`, `package/libs/libnftnl`,
`target/linux/x86/image` — so a change in `package/custom/` may interact with build-system surgery
described below. Read `docs/` (104 files, 49 hand-written validation records at last count) before
non-trivial work; nearly every subsystem has a design doc plus a validation record.

## Build commands

```bash
./scripts/feeds update -a          # fetch feeds AND bump registered custom recipe versions
./scripts/feeds install -a         # link feed packages into package/feeds/
make defconfig                     # normalize .config after edits
make prereq                        # host build prerequisites
make download                      # prefetch sources into dl/

make V=s                           # full build, verbose (V=99 for debug)
make package/<name>/compile V=s    # one package, e.g. package/custom/fastfetch/compile
make target/linux/compile V=s      # kernel only
make package/<name>/prepare|configure|install V=s
make target/linux/refresh          # regenerate quilt patches (or make package/<pkg>/refresh)
```

`./scripts/feeds update` is not a plain fetch here: after the other selected feeds succeed it runs
`scripts/update-custom-packages.py --update`, which queries upstream versions for every recipe
registered in `configs/custom-package-updates.json` and edits those recipes (GitHub-release
entries may also name `companion_assets` whose SHA-256 variables it refreshes and verifies).
Inspect local changes before running it, and use `./scripts/feeds update -i -a` when you only want
indexes. A new custom package **must** be registered in that JSON or the updater fails.

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

The snapshot and the working `.config` now describe the native **GNOME** desktop on Linux 7.3
(`CONFIG_PACKAGE_gnome-shell=y`, `weston` unset). `configs/gnome-desktop.config` is the fragment
that produced it: it disables `weston`, `seatd`, `libudev-zero` and `openwrt-desktop-launcher` and
selects `gnome-shell`, `gnome-remote-desktop`, `sunshine`, Flatpak/AppImage and the IME/audio
meta-packages. Preserve the existing `.config`; do not overwrite it with the snapshot unprompted.

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
`/etc/init.d/*` rc scripts in order), `openwrt-network-wait-online.service` (holds
`network-online.target` until netifd's static local interfaces such as `lan` are up; rootless
Quadlets depend on it). UCI, LuCI and rc scripts keep addressing procd-managed services, so most
router-side work is still procd-shaped. See `docs/systemd.md`.

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

**Kernel packages.** Kernels are distribution-style packages: each build N produces
`linux-image-<kver>-N-openwrt` (kernel plus *all* selected modules), `linux-headers-<release>`, and
the metapackages `linux-image-openwrt` / `kernel-dev-headers`; `kmod-*` keep only autoload and
modprobe configuration and are kernel-independent. The pack hook `scripts/kernel-package.py` stages
module/kernel/header trees under `build_dir/.../kernel-bundle/<release>/`; `package/kernel-bundle`
(`scripts/kernel-bundle.py`, invoked from `package/Makefile` before merge) builds and signs them.
On the router, `package/custom/openwrt-kernel-upgrade/files/kernelctl` (state schema 2 in
`/etc/openwrt-kernel/`, converting legacy schema-1 generations) acts as kernel-install/update-grub
from the APK hook, makes the newest kernel the GRUB default with a 3-attempt boot counter, blesses
it from `openwrt-kernel-boot.service` and prunes everything except the default, its fallback and
the rescue kernel.
Build numbers are reserved by `build-and-publish.py`; plain `make` targets do not reserve one. See
`docs/kernel-upgrade.md`.

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

### Router networking additions

Each is off by default or transparent, ported from coolsnowwolf/lede or upstream, and documented
in a guide + validation pair:

- **Full cone NAT** (`docs/fullcone-nat.md`) — a kernel netfilter patch
  (`CONFIG_NF_NAT_MASQUERADE_FULLCONE`), `libnftnl`/`nftables` patches, firewall4 patches and a
  LuCI firewall checkbox (feed patch `0029-luci-firewall-fullcone`). Enabled by
  `firewall.@defaults[0].fullcone='2'`; the kernel part needs a new kernel generation.
- **dnsmasq nftset fast path** (`docs/dnsmasq-nftset.md`) — dnsmasq adds plain address-set elements
  over netlink, and an nftables patch narrows the cache for single `add element` commands; anything
  else falls back to libnftables.
- **daed** (`package/custom/daed`, `luci-app-daed`, fragment `configs/daed.config`, `docs/daed.md`)
  — static Go binary shipped **disabled**; Passwall stays the default. The recipe re-pins the dae
  core to v2.1.1 under dae-wing and carries upstream backports plus local patches (including a
  vendored `third_party/outbound`). Its fragment turns on kernel BTF/`DEBUG_INFO`,
  `KERNEL_BPF_STREAM_PARSER` and `KERNEL_NETKIT` (new knobs in `config/Config-kernel.in`), so it
  changes the kernel ABI and needs a new generation.
- **ttyd over HTTPS** (`docs/ttyd-https.md`, feed patches `0027`/`0028`) reuses the uhttpd
  certificate so LuCI's terminal iframe is not blocked as mixed content.

### Feed modification model

`feeds/packages`, `feeds/video` and `feeds/luci` are **separate git repositories** that this fork
commits to. The main repo ignores `feeds/`. To keep those changes reviewable and restorable, they
are mirrored as patch series:

- `patches/feeds/NNNN-<feed>-<topic>.patch` — e.g. `0001-packages-local-integration.patch`,
  `0029-luci-firewall-fullcone.patch` (one numbered series across all feeds)
- `configs/*-feeds.json` — records each feed's upstream `base` and local `commit`
  (`configs/local-feeds.json` covers the main `packages`/`video` integration)

On a clean checkout with a matching baseline:
`git -C feeds/packages am "$PWD/patches/feeds/0001-packages-local-integration.patch"`, then
`./scripts/feeds install -a`. **Do not re-apply a patch when the feed working tree already contains
those commits**, and never reset a feed over local commits — a differing upstream baseline needs
review, not overwrite. See `docs/local-build.md` (Chinese).

### `package/custom/` layout

Wired in as a local feed by the last line of `feeds.conf.default`:
`src-link custom ../package/custom` (~390 tracked files). Recurring patterns:

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
- **Rust** — the host toolchain lives in `tools/` (`rust`, `bindgen`, `cbindgen`, `corrosion`,
  `sccache`); recipes use the `include/rust-*.mk` helpers.
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
(`configs/lan-apk-feeds.nginx.conf`, which allows the LAN `192.0.2.0/24` and WireGuard clients
`10.0.0.0/24`); `build-and-publish.py` orchestrates make → userspace publish → kernel generation,
importing the sibling scripts via `importlib`, locking on `tmp/.build-and-publish.lock`, and tracking
generations in `tmp/.kernel-publication-inputs.json`.
`--incremental` is compatibility-only; publication is always incremental. Each publication creates
an immutable `public/snapshots/` directory; `scripts/prune-lan-apk-feeds.py` (dry run by default,
`--apply` to delete) removes snapshots no symlink references.

Router side: `package/custom/lan-apk-feeds` is the consumer. `lan-apk-feeds-sync` writes
`/etc/apk/repositories.d/lan-local.list` with `<base>/kernel-upgrades/packages.adb` plus
`<base>/current/<repo>/packages.adb` for the `repositories=` list in `/etc/lan-apk-feeds.conf`
(userspace is kernel-independent; the publisher still keeps the legacy `abi/<config ABI>` alias).
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
                                             # test-systemd-service-bridge, test-merge-usr, test-needrestart,
                                             # test-network-wait-online
node scripts/tests/test-luci-<app>.js        # LuCI view logic, e.g. test-luci-daed-view,
                                             # test-luci-firewall-fullcone, test-luci-needrestart
sh scripts/tests/test-alternatives.sh        # alternative/symlink handling
sh scripts/test-<feature>.sh                 # appimage, distrobox, full-utils, native-libs,
                                             # native-build-tools, native-app-deps, podman-rootless
```

`scripts/tests/test-daed-vm.py` runs on the host but boots an exact image as a router+client KVM pair
(reusing `scripts/test-image-network.py`); it needs an image and never touches the physical router.

Some checks must run **on the target or a guest VM** after flashing or booting an image:
`scripts/tests/*-guest*.sh|py` (systemd, journald, libvirt, virt-manager, GNOME desktop, audio,
input, SSH, cgroups, needrestart), `firefox-smoke.sh`, `desktop-kernel-smoke.py`,
`sunshine-stream-*`, `kernel-upgrade/vm-console.py`, and the C probes (`appimage-probe.c`,
`virtio-egl-probe.c`, `spice-gl-reset.py`, `desktop-seat-retirement.c`). Despite its name,
`scripts/tests/test-libvirt-secondary-drivers.py` is also target-only: run it with `sudo` on the
router (read-only libvirt API probes; see `docs/libvirt.md`). For package builds prefer
`make package/<name>/compile V=s`; use `scripts/deptest.sh <package>` for dependency checks and
`scripts/checkpatch.pl` for C and kernel-adjacent patches. ELF/publication changes should also pass
`git diff --check`.

## Documentation and commit conventions

Every feature is documented as a pair: a guide `docs/<topic>.md` and a validation record
`docs/<topic>-validation.md` (49 validation files). Guides give setup commands, UCI option tables
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

- `GEMINI.md` is the equivalent guidance for Gemini CLI.
- `AGENTS.md` holds the shorter repository guidelines (layout, style, test naming, commit and
  workspace rules); this file expands on it. Its rules still apply: tabs in Makefile/C/shell/LuCI,
  four spaces in Python, `NNN-description.patch` names, focused commits with feed histories kept
  separate, explicit-path staging, and feed publication / device deployment only when explicitly
  authorized.
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
- **Retained, unselected APKs are part of publication.** Incremental feeds keep APKs for packages
  no longer in `.config`; they still need current ELF metadata and resolvable dependencies. See
  `docs/publication-readiness.md` before debugging a publish failure that a clean build didn't show.
- **Plain make does not reserve a kernel build number.** Use `build-and-publish.py build-only` or the
  wrappers for full builds; a plain full `make` with a published number would collide with published
  kmod identities.
- **Published APK identities are immutable.** Changed bytes require a new `PKG_RELEASE`; the ELF
  rebuild ledger is not permission to overwrite a released version.
- `package/custom/luci-theme-argon` and `package/luci-app-argon-config` are **embedded git repositories**
  (gitlinks with no `.gitmodules`). Commits inside them are not recorded by the parent repo; treat
  version selection there as a separate repository operation.
- `feeds/` is git-ignored but *is* source — `feeds/packages` and `feeds/video` hold local commits
  that the main repo only records as patches and JSON manifests. Never reset them.
- Untracked clutter that is not source: `.DS_Store`/`._.DS_Store`, backup tarballs,
  `scripts/__pycache__/`, `scripts/tests/__pycache__/`,
  `package/custom/openwrt-kernel-upgrade/files/__pycache__/`, `package/custom/fastfetch/.claude/`,
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
