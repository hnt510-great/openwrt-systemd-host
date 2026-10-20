# Repository Guidelines

## Project Structure & Module Organization

This OpenWrt tree includes an experimental x86_64/glibc/APK native-systemd variant. Build rules live in `Makefile`, `rules.mk`, and `include/`; target/kernel definitions are in `target/linux/`. Packages live in `package/`, including local additions in `package/custom/`. Independent feed repositories live in `feeds/`, linked through `package/feeds/`.

Use `tools/` for host tools, `toolchain/` for cross-compilers, `files/` for rootfs overlays, `configs/` for configuration snapshots and feed manifests, `docs/` for feature/validation guides, and `scripts/tests/` for helper tests. Treat `bin/`, `build_dir/`, `staging_dir/`, `tmp/`, and `dl/` as generated/downloaded artifacts.

## Build, Test, and Development Commands

Run from the repository root:

- `make prereq`: check host prerequisites.
- `./scripts/feeds update -a` / `./scripts/feeds install -a`: update feeds and link packages; inspect local feed changes first.
- `make menuconfig` / `make defconfig`: select and normalize configuration.
- `scripts/config/conf --fatalrecursive --defconfig=.config -w .config Config.in`: enforce strict Kconfig dependency validation.
- `make download`: prefetch sources.
- `make -j12 V=s`: build firmware; adjust parallelism to host capacity.
- `make package/custom/<name>/compile V=s`: compile a local package; use its actual path for other packages.

Native-systemd builds require `CONFIG_OPENWRT_SYSTEMD`, x86_64, glibc, and APK; outputs go under `bin/systemd/`. See `docs/systemd.md`. Publication is a separate action: follow `docs/lan-apk-feeds.md` and `docs/kernel-upgrade.md`.

## Coding Style & Naming Conventions

Follow nearby OpenWrt Makefiles: define `PKG_*` metadata, use package includes and `BuildPackage`, tabs in recipes, and `$(INSTALL_DIR)`, `$(INSTALL_BIN)`, and `$(INSTALL_DATA)`. Name patches `patches/001-description.patch`. Keep shell POSIX-compatible unless the script requires Bash; follow existing Python style. Use `scripts/checkpatch.pl` for relevant C/kernel patches.

## Testing Guidelines

Start with the affected package build. For kernel changes, run `make target/linux/compile V=s` and rebuild the image. Python helpers use `unittest`; run relevant `scripts/tests/test-*.py` files directly, for example `python3 scripts/tests/test-scheduled-maintenance.py`. Report skipped prerequisites. For runtime changes, boot the exact image and distinguish QEMU results from physical-device validation.

## Commit & Pull Request Guidelines

Use `area: imperative summary`, such as `build: preserve feed fixes for scheduled Kconfig validation`. Keep main-tree and feed commits separate. Follow `.github/pull_request_template`; describe affected packages/targets, configuration impact, linked issues, and validation.

## Agent-Specific Instructions

Preserve unrelated changes, `.config`, overlays, and feed histories; never broadly reset, clean, or stage. Do not edit generated directories or commit credentials/private keys. Keep host/target dependencies separate. Retain UCI/procd service ownership and the procd-recovery flashing path. Deploy only signed APKs matching the exact kernel ABI.
