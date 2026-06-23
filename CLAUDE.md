# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build System

OpenWrt uses a GNU Make-based cross-compilation framework. Build phases run in order: tools → toolchain → target/linux → package → package/index → image assembly.

### Common Commands

```bash
# Configuration
make menuconfig                    # Interactive target/package selection
make defconfig                     # Apply .config defaults
make kernel_menuconfig             # Linux kernel config

# Building
make V=s                           # Full build with verbose output
make package/<name>/compile V=s    # Build a single package
make target/linux/compile V=s      # Build kernel only
make download                      # Download all source archives
make clean                         # Remove build artifacts (keeps toolchain)
make dirclean                      # Full clean (removes toolchain too)
make distclean                     # Complete reset
make prereq                        # Check host build prerequisites
make package/index                 # Rebuild package index

# Feed management
./scripts/feeds update -a          # Clone/update all feeds
./scripts/feeds install -a         # Install symlinks for all feed packages
./scripts/feeds install <pkg>      # Install a specific feed package
./scripts/feeds list               # List available feeds

# Package development
make package/<name>/prepare V=s    # Fetch and unpack sources
make package/<name>/configure V=s  # Run configure step
make package/<name>/install V=s    # Install to staging dir
```

Pass `V=s` for verbose output, `V=99` for debug output.

## Project Architecture

### Top-Level Directories

| Directory | Purpose |
|-----------|---------|
| `package/` | Package build definitions (Makefiles with metadata + install steps) |
| `target/` | Target system definitions, kernel config, SDK, ImageBuilder |
| `toolchain/` | Cross-compiler components (gcc, binutils, musl/glibc, gdb) |
| `tools/` | Host-side tools built for the build machine |
| `include/` | Makefile includes: build rules, package templates, kernel rules |
| `scripts/` | Build scripts (feeds, package metadata, image generation) |
| `feeds/` | Cloned feed repositories |
| `dl/` | Downloaded source archives |
| `build_dir/` | Build workspace for target and host packages |
| `staging_dir/` | Host tools, target sysroot, toolchain |
| `files/` | Custom files overlaid onto target rootfs |
| `config/` | kconfig menu definitions |
| `bin/` | Build output (firmware images, packages) |

### Package Structure

Each package is a directory under `package/` with a `Makefile` following this pattern:

```makefile
include $(TOPDIR)/rules.mk

PKG_NAME:=<name>
PKG_VERSION:=<version>
PKG_RELEASE:=1
PKG_SOURCE:=<name>-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=<url>
PKG_HASH:=<sha256>

include $(INCLUDE_DIR)/package.mk

define Package/<name>
  SECTION:=<section>
  CATEGORY:=<category>
  TITLE:=<title>
  DEPENDS:=<dependencies>
endef

define Package/<name>/install
  $(INSTALL_DIR) $(1)/usr/bin
  $(INSTALL_BIN) $(PKG_BUILD_DIR)/<binary> $(1)/usr/bin/
endef

$(eval $(call BuildPackage,<name>))
```

Key variables in `rules.mk`: `TOPDIR`, `BUILD_DIR`, `STAGING_DIR`, `BIN_DIR`, `PACKAGE_DIR`, `DL_DIR`, `TARGET_DIR`, `INSTALL_BIN`, `INSTALL_DIR`, `INSTALL_DATA`.

### Package Categories

- `package/base-files/` — Essential system files
- `package/boot/` — Bootloaders
- `package/devel/` — Development tools
- `package/firmware/` — Firmware blobs
- `package/kernel/` — Kernel modules
- `package/libs/` — Libraries
- `package/network/` — Network (firewall, services, config)
- `package/system/` — System daemons (procd, ubus, uci, opkg/apk)
- `package/utils/` — Utilities
- `package/feeds/` — Symlinks to installed feed packages
- `package/custom/` — Custom local packages (not from feeds)

## Current Configuration

- **Target:** x86/64 (generic device)
- **Kernel:** Linux 6.18
- **Package manager:** APK (CONFIG_USE_APK=y)
- **Feeds configured:** passwall_packages, passwall_luci, taskplan, packages, luci, routing, telephony, video
- **Custom package:** node-bin (pre-compiled Node.js 24.14.1 for glibc x64)

## Key Conventions

- **Dependencies:** Add via `DEPENDS:` in `Package/<name>` definition. Use `@target` syntax for arch-specific deps (e.g., `@x86_64`). `+pkg` = build/run dependency, `+PACKAGE_pkg:pkg` = conditional dependency.
- **Install paths:** `$(1)` is the target root filesystem directory in install functions.
- **Version/substitution:** Defined in `include/version.mk` — uses sed-based template substitution.
- **Package scanning:** Metadata is extracted by `scripts/package-metadata.pl` into `tmp/.packageinfo`.
- **Reproducible builds:** Timestamps come from `SOURCE_DATE_EPOCH`; patches managed via quilt in `build_dir/`.

## External Documentation

- OpenWrt Developer Guide: https://openwrt.org/docs/guide-developer/start
- Build System Setup: https://openwrt.org/docs/guide-developer/build-system/install-buildsystem
- Upstream repository: https://github.com/openwrt/openwrt.git
