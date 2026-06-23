# GEMINI.md - OpenWrt Project Context

This project is an OpenWrt build system, a Linux-based operating system targeting embedded devices. It provides a framework for cross-compiling firmware images and individual software packages.

## Project Overview

- **Purpose:** Building customized Linux firmware for embedded devices (currently configured for x86_64).
- **Core Technologies:** GNU Make, kconfig, Shell scripting, C/C++, Lua (for LuCI web interface).
- **Package Management:** Uses `opkg` or `apk` (currently configured for APK via `CONFIG_USE_APK=y`).
- **Key Components:**
  - `package/`: Build definitions for software packages.
  - `target/`: Target system definitions and kernel configurations.
  - `toolchain/`: Cross-compiler components.
  - `tools/`: Build-host utilities.
  - `scripts/`: Utility scripts for feed management, metadata, and image generation.

## Common Workflows

### Setup and Configuration

```bash
# Update and install package feeds
./scripts/feeds update -a
./scripts/feeds install -a

# Open interactive configuration menu
make menuconfig

# Apply default configuration
make defconfig

# Configure the Linux kernel
make kernel_menuconfig
```

### Building

```bash
# Build the entire firmware (use V=s for verbose output)
make V=s

# Build a specific package
make package/<name>/compile V=s

# Clean build artifacts
make clean        # Removes bin/ and build_dir/
make dirclean     # Also removes staging_dir/ and toolchain/
make distclean    # Complete reset (removes .config and feeds)
```

### Package Development

Packages are defined by a `Makefile` that includes `$(TOPDIR)/rules.mk` and `$(INCLUDE_DIR)/package.mk`.

- **Location:** Typically under `package/` or symlinked from `feeds/`.
- **Custom Packages:** Found in `package/custom/`, `package/fastfetch/`, `package/searxng/`, etc.
- **Workflow:**
  ```bash
  make package/<name>/prepare V=s    # Fetch and unpack
  make package/<name>/configure V=s  # Run configure
  make package/<name>/compile V=s    # Compile
  make package/<name>/install V=s    # Install to staging_dir
  ```

## Development Conventions

- **Makefiles:** Follow the OpenWrt Makefile pattern. Use `$(INSTALL_DIR)`, `$(INSTALL_BIN)`, and `$(INSTALL_DATA)` for installation.
- **Dependencies:** Specified via `DEPENDS:=` in the `Package/<name>` definition.
- **Patches:** Managed via `quilt`. Patches should be placed in a `patches/` subdirectory within the package directory.
- **Debugging:** Always use `V=s` or `V=99` to diagnose build failures.
- **Architecture:** Strictly adhere to the separation of `host` (tools built for the build machine) and `target` (software built for the embedded device).

## Project-Specific Details

- **Target System:** x86/64
- **Kernel Version:** Linux 6.18
- **Package Manager:** APK
- **Custom Feeds:** Includes `passwall_packages`, `passwall_luci`, `taskplan`, among standard OpenWrt feeds.
- **Custom Additions:** The repository contains several custom packages like `fastfetch`, `searxng`, `luci-theme-argon`, etc.
