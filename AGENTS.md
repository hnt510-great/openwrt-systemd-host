# Repository Guidelines

## Project Structure & Module Organization

This customized OpenWrt tree includes x86_64/glibc, native systemd, desktop integration, and APK packaging. `package/` contains recipes; local packages live in `package/custom/`, with integration assets in `files/`, code in `src/`, and upstream changes in numbered `patches/`. `target/`, `toolchain/`, and `tools/` provide platform and build support. `feeds/` contains independent repositories; `package/feeds/` contains generated links. Root `files/` supplies image overlays. `configs/` holds configuration snapshots and feed manifests; `docs/` documents features and validation. Build outputs belong in `bin/`, `build_dir/`, and `staging_dir/`.

## Build, Test, and Development Commands

Run commands from the repository root:

- `./scripts/feeds update -a`: update feeds and custom recipe versions; inspect local changes first.
- `./scripts/feeds update -i -a`: regenerate indexes without updating upstream recipes.
- `./scripts/feeds install -a`: populate package links.
- `make menuconfig` / `make defconfig`: select options / normalize the existing configuration.
- `make download`: fetch selected sources.
- `make -j3 V=s`: build the configured firmware with verbose output.
- `make package/custom/<name>/compile V=s`: build one custom package.

Preserve the existing `.config`; use `docs/local-build.md` for configuration and feed reconstruction.

## Coding Style & Naming Conventions

Follow neighboring code. Use tabs for Makefile recipes and existing C, shell, and LuCI indentation; use four spaces in Python. Prefer lowercase, hyphenated package names and `001-description.patch` patch filenames. Keep durable changes outside generated build directories. Register every custom recipe in `configs/custom-package-updates.json`. Run `git diff --check`; use `scripts/checkpatch.pl` for applicable C patches.

## Testing Guidelines

Tests live in `scripts/tests/`: Python `unittest`, Node assertions, and guest smoke scripts. Name focused tests `test-<feature>.py` or `.js`. Examples:

```sh
python3 scripts/tests/test-custom-package-updates.py
node scripts/tests/test-luci-needrestart.js
```

Run relevant tests and package builds. Follow feature-specific `docs/*-validation.md` for guest checks. Report source checks, VM results, and physical-device validation separately; no repository-wide coverage threshold is defined.

## Commit & Pull Request Guidelines

Use the history's `component: imperative description` convention, such as `feeds: register new custom packages`. Keep commits focused and feed histories separate. PRs should explain behavior, affected configuration, and validation; link relevant issues and include screenshots for UI changes.

## Workspace & Security

Preserve unrelated edits, stashes, overlays, and nested repositories. Stage explicit paths. Exclude credentials, signing keys, backups, and generated artifacts. Treat feed publication and device deployment as separate, explicitly authorized operations.
