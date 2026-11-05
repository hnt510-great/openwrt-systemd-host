# GEMINI.md

This file provides guidance and workspace rules for Gemini / Antigravity when working with code in this repository.

---

## 1. Project Overview & Architecture

This repository is a customized OpenWrt fork tracking `openwrt/openwrt` `main` (~216 commits ahead). It builds an x86_64 "router plus desktop" system with several foundational divergences from upstream:

- **glibc C library**: Uses glibc instead of musl (`CONFIG_LIBC_USE_GLIBC=y`, `CONFIG_USE_GLIBC=y`).
- **APK package manager**: Uses signed APK packages instead of opkg (`CONFIG_USE_APK=y`, `CONFIG_SIGNED_PACKAGES=y`).
- **Native systemd**: Runs native systemd as PID 1 alongside a retained procd (`CONFIG_OPENWRT_SYSTEMD=y`).
- **Mainline Linux 7.3**: Target `x86/64` runs mainline Linux 7.3 (`CONFIG_LINUX_7_3=y`); the versioned 6.18 configuration is retained.
- **GNOME Desktop Session**: Shared-user GNOME 51 desktop on VT7 (local display, LAN RDP via `gnome-remote-desktop`, Sunshine/Moonlight).
- **Core build-system surgery**: Modifies core upstream files (`include/kernel.mk`, `include/package-pack.mk`, `include/package.mk`, `include/rootfs.mk`, `package/base-files`, `package/system/{apk,procd,systemd}`, `target/linux/x86/image`). Always inspect interactions before modifying custom recipes.

Outputs:
- Systemd images and native APK feeds land in `bin/systemd/`.
- Stock images stay in `bin/targets/`.

---

## 2. Essential Commands

### Feeds & Packages
```bash
./scripts/feeds update -a          # Fetch feeds AND bump registered custom recipes via update-custom-packages.py
./scripts/feeds update -i -a       # Regenerate indexes ONLY (no upstream version queries)
./scripts/feeds install -a         # Link feed packages into package/feeds/
```
> [!IMPORTANT]
> `./scripts/feeds update -a` automatically queries upstream versions for recipes registered in `configs/custom-package-updates.json` and edits them. Inspect changes before running, or use `-i -a` when only index regeneration is needed.

### Configuration
```bash
make defconfig                     # Normalize existing .config
make prereq                        # Check host prerequisites
make download                      # Prefetch sources into dl/

# Merging a kconfig fragment:
./scripts/kconfig.pl + .config configs/<feature>.config > .config.new && mv .config.new .config && make defconfig
```
> [!NOTE]
> Do NOT use `scripts/diffconfig.sh` to minimize config; circular Kconfig dependencies (Mesa, glib2-gir, openwrt-desktop) make it unreliable. The full baseline is stored in `configs/x86-64-systemd-desktop.config`. Preserve `.config` unless explicitly instructed to overwrite it.

### Build Targets
```bash
make -j$(nproc) V=s                # Full firmware build (verbose)
make package/<name>/compile V=s    # Build a single package (e.g., package/custom/fastfetch/compile)
make target/linux/compile V=s      # Build kernel only
make package/<name>/prepare V=s    # Prepare sources (unpack + patch)
make package/<name>/refresh        # Refresh quilt patches for a package
make target/linux/refresh          # Refresh quilt patches for target kernel
```

### Publication & Upgrades
```bash
./scripts/build-and-publish.sh -j16           # Build and publish userspace APKs and kernel generation
./scripts/publish-changed-feeds.sh [--dry-run] # Preflight simulation against live router, then publish
python3 scripts/build-and-publish.py build-only -j12 V=s  # Reserve generation and build, do not publish
python3 scripts/update-mainline-kernel.py --check|--update # Check or update mainline point releases
```

---

## 3. Configuration & Feed Management

- **Configuration Baseline**: `configs/x86-64-systemd-desktop.config` (356 KB) is the master configuration. Reproduce with:
  `cp configs/x86-64-systemd-desktop.config .config && make defconfig`
- **Configuration Fragments**: `configs/<feature>.config` contain partial Kconfig settings merged via `scripts/kconfig.pl`.
- **Feed Manifests**: `configs/*-feeds.json` define upstream base commit, local commit, and patches for each feed. `configs/lan-apk-feeds.json` holds publication targets (`/srv/openwrt-feeds`, served via nginx `lan-apk-feeds.service`).
- **Independent Feed Repositories**: `feeds/packages` and `feeds/video` are independent Git repos with local commits. The root repo ignores `feeds/`, but changes are tracked as patch series in `patches/feeds/NNNN-<feed>-<topic>.patch`.
  - Never reset or wipe `feeds/` working trees without checking local commits.
  - To apply feed patches on a clean base: `git -C feeds/packages am "$PWD/patches/feeds/0001-packages-local-integration.patch"`.

---

## 4. Key Subsystems & Design

### Dual-Init Architecture (systemd + procd)
- `/sbin/init` performs early mounts, runs preinit, and mounts overlayfs.
- GRUB default passes `openwrt.init=systemd` to exec systemd as PID 1; fallback or `openwrt.init=procd` boots procd.
- Bridge units live in `package/system/systemd-openwrt/`:
  - `openwrt-ubusd.service`: Starts ubus daemon.
  - `openwrt-procd.service`: `procd --systemd=units`, the OpenWrt service API (ubus `service`/`system`/`hotplug.*`, triggers, validation) and `/etc/hotplug.d` handlers fed by udev.
    Each instance registered through `procd.sh` runs as a transient `openwrt-SERVICE@INSTANCE.service` in `openwrt-SERVICE.slice` (procd patch `130-systemd-transient-units.patch`); vrf/trace/bundle/descriptor-passing instances fall back to procd children in scopes.
    The systemd manager owns the hardware watchdog. Rollback to procd supervision is a `--systemd` drop-in plus `RuntimeWatchdogSec=0`. See `docs/systemd-native-supervision.md`.
  - `openwrt-services.service`: Runs `/etc/init.d/*` rc scripts in sequence.
  - `openwrt-network-wait-online.service`: Holds `network-online.target` until netifd brings static local interfaces (e.g., `lan`) up.
- **Merged `/usr`**: `scripts/merge-usr.py` transforms rootfs layout, redirecting `/bin`, `/sbin`, and `/lib` to `/usr/...`. BusyBox conflicts are handled via `ALTERNATIVE_COMMANDS`.

### GNOME Desktop Profile
- Meta-package: `package/custom/openwrt-desktop` launches GNOME 51 on VT7 under an unprivileged user session via PAM/logind (no display manager).
- Shared display: `gnome-remote-desktop` (RDP, LAN IPv4 only) and Sunshine (Moonlight).
- Companion packages: `openwrt-desktop-ime` (Fcitx5 + Kimpanel), `openwrt-desktop-audio` (PipeWire/PulseAudio adapter).
- On-device setup commands (run as root):
  ```sh
  desktop-setup USER
  desktop-rdp-setup USER [--password-stdin]
  sunshine-setup USER --capture=portal|--enable-kms
  desktop-audio-setup USER
  ```
- Keyring credentials use systemd `LoadCredential` under `/etc/desktop/gnome/`. Never hardcode user passwords in images.

### Mainline Kernel & Parallel Generations
- Mainline series: Linux 7.3 tracked in `target/linux/x86/64`. `scripts/update-mainline-kernel.py` verifies SHA-256 and applies backport/pending/hack patches with zero fuzz.
- Generations: `package/custom/openwrt-kernel-upgrade` enables parallel ABI-pinned kernels with GRUB recovery.
  - Runtime management: `/usr/sbin/kernelctl` (Python 3) with state in `/etc/openwrt-kernel/`.
  - Host scripts: `scripts/kernel-build-inputs.py` fingerprints inputs; `scripts/publish-kernel-upgrade-feed.py` handles feed publishing.
  - Generation allocation: Reserved by `build-and-publish.py`. Plain `make` targets do NOT reserve a generation.

### ELF ABI & Signed APK Packaging
- Packaging declares ELF shared-library contracts (`so:<SONAME>=0`) scanned via `scripts/elf-abi.py` into `/usr/lib/apk/packages/<name>.elf.json`.
- Ucode ABI is tracked separately via `scripts/ucode-abi.py`.
- Rebuild ledger: `configs/apk-elf-rebuilds.mk` manages metadata migrations without editing recipes.
- Target migration: `scripts/apply-elf-migration.py` includes a 20-minute systemd rollback timer.
- Package immutability: Published packages are immutable; any byte change requires bumping `PKG_RELEASE`.

### APK Upgrade Preflight & Publication Gate
- `scripts/publish-changed-feeds.sh` is the production publication gate.
- Strict requirements:
  - Connects to physical router via SSH (`upgrade_preflight.ssh_target` in `configs/lan-apk-feeds.json`, currently `desktop-user@192.0.2.1`).
  - Reads installed package state under APK lock.
  - Simulates upgrade transactions with `scripts/apk-upgrade-preflight.py` (`--plan-json`, `--userspace-only`).
  - Halts if router is unreachable, has pending kernel trial, or simulation encounters blockers.
- Packages are published to host `/srv/openwrt-feeds`, never pushed directly into target router storage.

### `package/custom/` Local Packages
- Wired via `feeds.conf.default`: `src-link custom ../package/custom`.
- Patterns:
  - Prebuilt binary repacks (`cmake-bin`, `node-bin`, `firefox-esr-bin`) gated on `@TARGET_x86_64 @USE_GLIBC`.
  - Distro compatibility (`glibc-distro-compat`, `glibc-getent`, `glibc-locale-utf8`).
  - Native target development (`native-libs-dev`, `kernel-dev-headers`, `native-build-deps`).
  - Shared Xorg/Meson makefile fragments: `xorg-client.mk`, `xorg-meson.mk`.
- **Registration requirement**: Every recipe in `package/custom/` must be registered in `configs/custom-package-updates.json`.

---

## 5. Testing & Verification

No single monolithic test command exists. Run targeted tests:

### Host Tests
```bash
python3 scripts/tests/test-<topic>.py    # e.g., test-elf-abi, test-ucode-abi, test-lan-apk-publisher,
                                         # test-kernel-upgrade, test-merge-usr, test-needrestart, etc.
node scripts/tests/test-<app>-view.js    # LuCI views
sh scripts/tests/test-alternatives.sh    # Alternatives/symlinks
scripts/deptest.sh <package>             # Dependency validation
scripts/checkpatch.pl <patch-file>       # Patch format verification
git diff --check                         # Whitespace & formatting check
```

### Guest VM & Target Tests
- Integration tests intended for VM or target: `scripts/tests/*-guest*.sh|py`, `firefox-smoke.sh`, `desktop-kernel-smoke.py`, `test-image-network.py`.
- `scripts/tests/test-libvirt-secondary-drivers.py` requires `sudo` on the target device.

### Documentation Requirements
Every non-trivial feature must maintain a documentation pair:
1. Feature guide: `docs/<feature>.md` (setup, architecture, configuration).
2. Validation record: `docs/<feature>-validation.md` (hand-written check table, target SHA-256, evidence path in `/srv/openwrt-validation/...`).

---

## 6. Coding Style & Conventions

- **Makefiles, C, Shell, LuCI**: Use hard tabs for indentation.
- **Python**: Use four spaces for indentation (PEP 8).
- **Patches**:
  - OpenWrt patches must be quilt-managed (`make package/<pkg>/refresh`, `make target/linux/refresh`), NEVER generated via `git format-patch`.
  - Patches follow `NNN-description.patch` naming.
- **Git Commits**:
  - Format: `area: imperative summary` (e.g., `systemd: update unit dependencies`, `apk: bump elf abi ledger`).
  - Keep main repository commits and feed repository commits cleanly separated.

---

## 7. Guardrails & Safety Rules

> [!CAUTION]
> Adhere strictly to the following constraints:
> 
> 1. **Automated Scheduled Maintenance is DISABLED**: Do not re-enable the 72-hour cron job or background automation without explicit user request.
> 2. **Never push directly to physical router**: Production publication writes to the LAN feed destination (`/srv/openwrt-feeds`). Deployment to the router is a separate, user-authorized step.
> 3. **Preserve unversioned files in `files/`**:
>    - Only 11 files in `files/` are versioned:
>      - `files/etc/config/fstab`
>      - `files/etc/skel/.zshrc`
>      - `files/etc/ssh/sshd_config.d/00-openwrt-access.conf`
>      - `files/etc/sudoers.d/10-multiuser`
>      - `files/etc/uci-defaults/{99-multiuser,99-openssh-access,99-uhttpd-luci,99-zsh-default}`
>      - `files/etc/zsh/zshrc`
>      - `files/lib/upgrade/keep.d/{multiuser,openssh-access}`
>    - All other files in `files/` (e.g., `99-local-user`, private credentials, network configs) are unversioned. Do NOT stage or commit them.
> 4. **Embedded Submodules**: `package/custom/luci-theme-argon` and `package/luci-app-argon-config` are embedded Git repositories without `.gitmodules`. Do not stage unintended changes inside them.
> 5. **Immutable Packages**: Never overwrite a published APK release without incrementing `PKG_RELEASE`.
> 6. **Feeds Working Tree**: Do not hard-reset `feeds/packages` or `feeds/video`; they contain live local branches.
