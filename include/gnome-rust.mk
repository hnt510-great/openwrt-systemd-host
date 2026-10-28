# Rust libraries built by GNOME's Meson projects. Cargo.lock fixes dependency
# versions and checksums. Fetch once during preparation; compile offline.
include $(TOPDIR)/feeds/packages/lang/rust/rust-values.mk

GNOME_RUST_VARS=$(CARGO_PKG_CONFIG_VARS) \
	CARGO_NET_OFFLINE=true CARGO_BUILD_JOBS=2 CARGO_PROFILE_RELEASE_LTO=false PKG_CONFIG_ALLOW_CROSS=1 \
	RUSTC="$(STAGING_DIR)/host/bin/rustc" \
	PATH="$(STAGING_DIR)/host/bin:$(STAGING_DIR_HOSTPKG)/bin:$(TARGET_PATH)" \
	PKG_CONFIG_LIBDIR="$(STAGING_DIR)/usr/lib/pkgconfig:$(STAGING_DIR)/usr/share/pkgconfig"
MESON_VARS += $(GNOME_RUST_VARS)
MESON_ARGS += -Db_lto=false
PKG_FILE_DEPENDS += $(INCLUDE_DIR)/gnome-rust.mk $(TOPDIR)/scripts/gnome-uninstalled-pc.py

# Cargo custom targets run again during installation. Keep their target
# compiler, linker and pkg-config environment identical to compilation.
define Build/Install
	+$(MESON_VARS) DESTDIR="$(PKG_INSTALL_DIR)" $(NINJA) -C $(MESON_BUILD_DIR) install
endef

define Build/Prepare
	$(call Build/Prepare/Default)
	cd $(PKG_BUILD_DIR) && CARGO_HOME="$(DL_DIR)/cargo" \
		$(STAGING_DIR)/host/bin/cargo fetch --locked --target $(RUSTC_TARGET_ARCH)
endef

define Build/Configure
	$(call Meson/CreateNativeFile,$(PKG_BUILD_DIR)/openwrt-native.txt)
	$(call Meson/CreateCrossFile,$(PKG_BUILD_DIR)/openwrt-cross.txt)
	$(SED) "/^\[binaries\]/a rust = '$(STAGING_DIR)/host/bin/rustc'\nexe_wrapper = '$(TOPDIR)/scripts/gi-target-runner'" $(PKG_BUILD_DIR)/openwrt-cross.txt
	$(SED) "/^\[properties\]/a rust_target = '$(RUSTC_TARGET_ARCH)'" $(PKG_BUILD_DIR)/openwrt-cross.txt
	$(call Meson,setup --buildtype plain --native-file $(PKG_BUILD_DIR)/openwrt-native.txt \
		--cross-file $(PKG_BUILD_DIR)/openwrt-cross.txt -Ddefault_library=shared \
		$(MESON_ARGS) $(MESON_BUILD_DIR) $(MESON_BUILD_DIR)/..,$(MESON_VARS))
	$(STAGING_DIR_HOSTPKG)/bin/python3 $(TOPDIR)/scripts/gnome-uninstalled-pc.py $(MESON_BUILD_DIR)/meson-uninstalled
endef
