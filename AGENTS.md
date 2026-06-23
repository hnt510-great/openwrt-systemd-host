# Repository Guidelines

## Project Structure & Module Organization

This repository is an OpenWrt build tree. Top-level build rules live in `Makefile`, `rules.mk`, and `include/`. Package definitions are under `package/`; installed feed packages are linked under `package/feeds/`, while local additions may live in `package/custom/` or standalone package directories. Target definitions, kernel configs, and image logic are in `target/linux/<target>/`. Host tools are in `tools/`, toolchain components in `toolchain/`, helper scripts in `scripts/`, and root filesystem overlays in `files/`.

Generated or downloaded content includes `bin/`, `build_dir/`, `staging_dir/`, `tmp/`, and `dl/`. Treat these as build artifacts, not source.

## Build, Test, and Development Commands

- `./scripts/feeds update -a`: fetch or update configured package feeds.
- `./scripts/feeds install -a`: link feed packages into `package/feeds/`.
- `make menuconfig`: select target, firmware options, and packages.
- `make defconfig`: normalize `.config` after option changes.
- `make prereq`: verify required host tools.
- `make download`: prefetch source archives into `dl/`.
- `make V=s`: build firmware with verbose output.
- `make package/<name>/compile V=s`: build one package, for example `make package/fastfetch/compile`.
- `make clean`: remove normal build outputs; use `dirclean` or `distclean` only when a full rebuild/reset is intended.

## Coding Style & Naming Conventions

Follow OpenWrt package Makefile conventions: include `$(TOPDIR)/rules.mk`, define `PKG_*` metadata, include `$(INCLUDE_DIR)/package.mk`, and finish with `$(eval $(call BuildPackage,<name>))`. Use tabs for Make recipe lines. Use `$(INSTALL_DIR)`, `$(INSTALL_BIN)`, and `$(INSTALL_DATA)` in install sections. Store patches in `patches/` with numeric prefixes such as `001-fix-build.patch`.

Shell scripts should stay POSIX-compatible unless an existing script requires otherwise. For C and kernel-adjacent changes, use the local `scripts/checkpatch.pl` where practical.

## Testing Guidelines

There is no single repository-wide unit test command. Validate changes with the narrowest relevant build first. For package work, run `make package/<name>/compile V=s`; for kernel or target changes, run `make target/linux/compile V=s` and an image build if output is affected. Dependency checks can use `scripts/deptest.sh <package>` after feeds are installed.

## Commit & Pull Request Guidelines

Recent history uses scoped subjects such as `uhttpd: update to Git HEAD` and `build: fix apk_package_files wildcard for packages without ABI version`. Use `area: imperative summary`, keep the subject concise, and explain behavior changes, configuration impact, and test results.

Pull requests should follow the OpenWrt submitting-patches guidance linked from `.github/pull_request_template`. Include affected target/package, issue links, and validation commands.

## Agent-Specific Instructions

Do not edit generated build directories or revert unrelated local changes. Keep edits focused and preserve the host-versus-target build separation.
