include $(TOPDIR)/rules.mk
PKG_NAME:=adwaita-icons
PKG_VERSION:=3.38.0
PKG_RELEASE:=1
PKG_SOURCE:=adwaita-icon-theme-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/adwaita-icon-theme/3.38/
PKG_HASH:=6683a1aaf2430ccd9ea638dd4bfe1002bc92b412050c3dba20e480f979faaf97
PKG_BUILD_DIR:=$(BUILD_DIR)/adwaita-icon-theme-$(PKG_VERSION)
PKG_LICENSE:=CC-BY-SA-3.0 LGPL-3.0-or-later
PKG_BUILD_DEPENDS:=python3/host
include $(INCLUDE_DIR)/package.mk
define Package/adwaita-icons
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=adwaita-icon-theme
  DEPENDS:=+hicolor-icon-theme
endef

define Build/Compile
	$(STAGING_DIR_HOSTPKG)/bin/python3 ./files/build-index.py $(PKG_BUILD_DIR)
endef

define Package/adwaita-icons/install
	$(INSTALL_DIR) $(1)/usr/share/icons/Adwaita
	$(CP) $(PKG_BUILD_DIR)/index.theme $(1)/usr/share/icons/Adwaita/
	$(foreach size,16 22 24 32 48 64 96 256,$(CP) $(PKG_BUILD_DIR)/Adwaita/$(size)x$(size) $(1)/usr/share/icons/Adwaita/;)
endef
$(eval $(call BuildPackage,adwaita-icons))
