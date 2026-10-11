include $(TOPDIR)/rules.mk
PKG_NAME:=hicolor-icon-theme
PKG_VERSION:=0.18
PKG_RELEASE:=1
PKG_SOURCE:=hicolor-icon-theme-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://icon-theme.freedesktop.org/releases/
PKG_HASH:=db0e50a80aa3bf64bb45cbca5cf9f75efd9348cf2ac690b907435238c3cf81d7
PKG_BUILD_DIR:=$(BUILD_DIR)/hicolor-icon-theme-$(PKG_VERSION)
PKG_LICENSE:=GPL-2.0-or-later
PKG_BUILD_DEPENDS:=python3/host
include $(INCLUDE_DIR)/package.mk
define Package/hicolor-icon-theme
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=hicolor-icon-theme
endef

define Build/Compile
endef

define Package/hicolor-icon-theme/install
	$(INSTALL_DIR) $(1)/usr/share/icons/hicolor
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/index.theme $(1)/usr/share/icons/hicolor/
endef
$(eval $(call BuildPackage,hicolor-icon-theme))
