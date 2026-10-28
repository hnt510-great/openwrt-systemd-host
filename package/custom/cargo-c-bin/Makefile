include $(TOPDIR)/rules.mk

PKG_NAME:=cargo-c-bin
PKG_VERSION:=0.10.26
PKG_RELEASE:=1
PKG_SOURCE:=cargo-c-$(PKG_VERSION)-x86_64-linux-musl.tar.gz
PKG_SOURCE_URL:=https://github.com/lu-zero/cargo-c/releases/download/v$(PKG_VERSION)/cargo-c-x86_64-unknown-linux-musl.tar.gz?
PKG_HASH:=685fab5a2e1539c5075cea21c42469ee5a489d877dbdbf7adccf4bb631d77545
PKG_LICENSE:=MIT
PKG_HOST_ONLY:=1
HOST_UNPACK=mkdir -p $(HOST_BUILD_DIR); $(TAR) -xf $(DL_DIR)/$(PKG_SOURCE) -C $(HOST_BUILD_DIR)

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/host-build.mk

define Package/cargo-c-bin
  SECTION:=devel
  CATEGORY:=Development
  TITLE:=Official cargo-c host tools (Linux x86_64)
  BUILDONLY:=1
endef

define Host/Configure
endef

define Host/Compile
endef

define Host/Install
	$(INSTALL_DIR) $(STAGING_DIR_HOSTPKG)/bin
	$(INSTALL_BIN) $(HOST_BUILD_DIR)/cargo-c* $(STAGING_DIR_HOSTPKG)/bin/
endef

$(eval $(call HostBuild))
$(eval $(call BuildPackage,cargo-c-bin))
