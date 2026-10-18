# Include after meson.mk. This integration is opt-in for x86_64/glibc packages.
# Both variants are needed: the host build supplies g-ir-scanner at build time,
# while the target package's InstallDev publishes gobject-introspection-1.0.pc
# and the target g-ir-* wrappers into staging. Without the plain dependency the
# .pc is missing whenever a consumer configures before the target package.
PKG_BUILD_DEPENDS += gobject-introspection/host gobject-introspection
MESON_USE_STAGING_PYTHON:=1
PYTHON_BIN:=$(STAGING_DIR_HOSTPKG)/bin/python3
MESON_VARS += PATH="$(STAGING_DIR_HOSTPKG)/bin:$(TARGET_PATH)" \
	GI_CROSS_LAUNCHER="$(TOPDIR)/scripts/gi-target-runner" \
	CC="$(TARGET_CC)" CFLAGS="$(TARGET_CFLAGS) $(TARGET_CPPFLAGS)" \
	LDFLAGS="$(TARGET_LDFLAGS)" PKG_CONFIG="$(PKG_CONFIG)"

define Build/Configure
	$(call Meson/CreateNativeFile,$(PKG_BUILD_DIR)/openwrt-native.txt)
	$(call Meson/CreateCrossFile,$(PKG_BUILD_DIR)/openwrt-cross.txt)
	$(SED) "/^\[binaries\]/a exe_wrapper = '$(TOPDIR)/scripts/gi-target-runner'" $(PKG_BUILD_DIR)/openwrt-cross.txt
	$(call Meson,setup --buildtype plain --native-file $(PKG_BUILD_DIR)/openwrt-native.txt \
		--cross-file $(PKG_BUILD_DIR)/openwrt-cross.txt -Ddefault_library=shared \
		$(MESON_ARGS) $(MESON_BUILD_DIR) $(MESON_BUILD_DIR)/..,$(MESON_VARS))
endef
