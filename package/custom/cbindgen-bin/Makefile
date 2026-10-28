include $(TOPDIR)/rules.mk

PKG_NAME:=cbindgen-bin
PKG_VERSION:=0.29.4
PKG_RELEASE:=1
PKG_SOURCE:=cbindgen-$(PKG_VERSION)-linux-x86_64.bin
PKG_SOURCE_URL:=https://github.com/mozilla/cbindgen/releases/download/$(PKG_VERSION)/cbindgen-ubuntu22.04?
PKG_HASH:=27ac237e2ad3ffaffc8ecce0c03e3caa1d1b09e691906c3cb0967367ff6d783d
PKG_LICENSE:=MPL-2.0
PKG_HOST_ONLY:=1
HOST_UNPACK=mkdir -p $(HOST_BUILD_DIR); cp $(DL_DIR)/$(PKG_SOURCE) $(HOST_BUILD_DIR)/cbindgen

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/host-build.mk

define Package/cbindgen-bin
  SECTION:=devel
  CATEGORY:=Development
  TITLE:=Official Mozilla cbindgen host binary (Linux x86_64)
  BUILDONLY:=1
endef

define Host/Configure
endef

define Host/Compile
endef

define Host/Install
	$(INSTALL_DIR) $(STAGING_DIR_HOSTPKG)/bin
	$(INSTALL_BIN) $(HOST_BUILD_DIR)/cbindgen $(STAGING_DIR_HOSTPKG)/bin/
endef

$(eval $(call HostBuild))
$(eval $(call BuildPackage,cbindgen-bin))
