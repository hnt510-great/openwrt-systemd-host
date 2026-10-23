include $(TOPDIR)/rules.mk

PKG_NAME:=libva-utils
PKG_VERSION:=2.24.0
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=https://codeload.github.com/intel/libva-utils/tar.gz/$(PKG_VERSION)?
PKG_HASH:=bf959a1ced3cde8176a7ff50ad358ee98e93301ac068581a8b2617c5b83afcb3
PKG_LICENSE:=MIT
PKG_LICENSE_FILES:=COPYING

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/meson.mk

define Package/libva-utils
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=VA-API driver capability checker (vainfo)
  URL:=https://github.com/intel/libva-utils
  DEPENDS:=+libva +libdrm +libwayland
endef

MESON_ARGS += -Ddrm=true -Dwayland=true -Dx11=false -Dwin32=false -Dtests=false

define Build/Compile
	$(call Build/Compile/Meson,vainfo/vainfo)
endef

define Build/Install
endef

define Package/libva-utils/install
	$(INSTALL_DIR) $(1)/usr/bin $(1)/usr/share/licenses/libva-utils
	$(INSTALL_BIN) $(MESON_BUILD_DIR)/vainfo/vainfo $(1)/usr/bin/
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/COPYING $(1)/usr/share/licenses/libva-utils/
endef

$(eval $(call BuildPackage,libva-utils))
