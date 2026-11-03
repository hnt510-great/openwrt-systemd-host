# Repository Guidelines

## Project Structure & Module Organization

This customized OpenWrt tree targets x86_64 with glibc, APK, native systemd, mainline Linux 7.3, and a shared-user GNOME desktop. `package/` contains recipes; local packages live in `package/custom/`, with integration assets in `files/`, code in `src/`, and upstream changes in numbered `patches/`. `target/`, `toolchain/`, and `tools/` provide platform and build support, including the Rust host toolchain (`tools/rust`, `bindgen`, `cbindgen`, `corrosion`, `sccache`) and `include/rust-*.mk` helpers. `feeds/` contains independent repositories with local commits, mirrored as `patches/feeds/` and `configs/*-feeds.json`; `package/feeds/` contains generated links. Root `files/` supplies image overlays and is mostly unversioned. `configs/` holds the full `x86-64-systemd-desktop.config` snapshot, feature fragments, and feed/publication manifests; `docs/` pairs each feature guide with a `*-validation.md` record. Build outputs belong in `bin/` (native systemd output in `bin/systemd`), `build_dir/`, and `staging_dir/`. `CLAUDE.md` gives the detailed architecture.

## Build, Test, and Development Commands

Run commands from the repository root:

- `./scripts/feeds update -a`: update feeds and custom recipe versions; inspect local changes first.
- `./scripts/feeds update -i -a`: regenerate indexes without updating upstream recipes.
- `./scripts/feeds install -a`: populate package links.
- `make menuconfig` / `make defconfig`: select options / normalize the existing configuration.
- `make download`: fetch selected sources.
- `make -j3 V=s`: build the configured firmware with verbose output.
- `make package/custom/<name>/compile V=s`: build one custom package.
- `python3 scripts/build-and-publish.py build-only -j12 V=s`: full build that reserves a kernel generation without publishing.
- `python3 scripts/update-mainline-kernel.py --check`: compare the kernel series with kernel.org.

Preserve the existing `.config`; merge `configs/<feature>.config` fragments with `scripts/kconfig.pl` and use `docs/local-build.md` for configuration and feed reconstruction. Plain `make` does not reserve a kernel generation; never pair a new image with old-ABI modules or headers.

## Coding Style & Naming Conventions

Follow neighboring code. Use tabs for Makefile recipes and existing C, shell, and LuCI indentation; use four spaces in Python. Prefer lowercase, hyphenated package names and `001-description.patch` patch filenames. Regenerate quilt patches with `make target/linux/refresh` or `make package/<pkg>/refresh`, not `git format-patch`. Keep durable changes outside generated build directories. Register every custom recipe in `configs/custom-package-updates.json`. Published APK identities are immutable: changed package bytes require a new `PKG_RELEASE`. Run `git diff --check`; use `scripts/checkpatch.pl` for applicable C patches.

## Testing Guidelines

Tests live in `scripts/tests/`: Python `unittest`, Node assertions, and guest smoke scripts. Name focused tests `test-<feature>.py` or `.js`. Examples:

```sh
python3 scripts/tests/test-custom-package-updates.py
python3 scripts/tests/test-network-wait-online.py
node scripts/tests/test-luci-needrestart.js
```

Run relevant tests and package builds. `*-guest*` scripts, the C probes, and `test-libvirt-secondary-drivers.py` run on the target or a guest VM. Follow feature-specific `docs/*-validation.md` for guest checks. Report source checks, VM results, and physical-device validation separately; no repository-wide coverage threshold is defined.

## Commit & Pull Request Guidelines

Use the history's `component: imperative description` convention, such as `feeds: register new custom packages`. Keep commits focused and feed histories separate; feature commits usually include code, config updates, and both docs. PRs should explain behavior, affected configuration, and validation; link relevant issues and include screenshots for UI changes.

## Workspace & Security

Preserve unrelated edits, stashes, overlays, feed commits, and the `luci-theme-argon` submodule. Never reset `feeds/`. Stage explicit paths. Exclude credentials, signing keys, personal `files/` overlays, backups, and generated artifacts. Treat feed publication and device deployment as separate, explicitly authorized operations; publication is gated on a reachable router preflight (`configs/lan-apk-feeds.json`). Scheduled host maintenance is disabled; do not reinstall its cron job unless asked.
