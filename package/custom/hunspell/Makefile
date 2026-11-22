include $(TOPDIR)/rules.mk

PKG_NAME:=hunspell
PKG_VERSION:=1.7.6
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=https://github.com/hunspell/hunspell/releases/download/v$(PKG_VERSION)/
PKG_HASH:=9c650ace31d4d8cc1da925a9507c3de1d50f1a54857af2f72429f517d5d53467
PKG_LICENSE:=LGPL-2.1-or-later GPL-2.0-or-later MPL-1.1
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1

include $(INCLUDE_DIR)/package.mk

# The interactive UI is the only part that would need curses.
CONFIGURE_ARGS += --without-ui

define Package/hunspell
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=Hunspell spell checker library and tool
  URL:=https://hunspell.github.io/
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +libstdcpp
endef

define Package/hunspell/install
	$(INSTALL_DIR) $(1)/usr/lib $(1)/usr/bin
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libhunspell-*.so* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/bin/hunspell $(1)/usr/bin/
endef

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/include $(1)/usr/lib $(1)/usr/lib/pkgconfig
	$(CP) $(PKG_INSTALL_DIR)/usr/include/hunspell $(1)/usr/include/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libhunspell-*.so* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/hunspell.pc $(1)/usr/lib/pkgconfig/
endef

$(eval $(call BuildPackage,hunspell))
