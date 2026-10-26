include $(TOPDIR)/rules.mk

PKG_NAME:=openwrt-desktop-launcher
PKG_VERSION:=1
PKG_RELEASE:=1
PKG_LICENSE:=MIT

include $(INCLUDE_DIR)/package.mk

define Package/openwrt-desktop-launcher
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Searchable application launcher for Weston
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +libgtk3 +glib2
endef

define Build/Compile
	$(TARGET_CC) $(TARGET_CFLAGS) $(TARGET_CPPFLAGS) -Wall -Wextra \
		-o $(PKG_BUILD_DIR)/desktop-applications ./src/desktop-applications.c \
		$(TARGET_LDFLAGS) $$$$($(PKG_CONFIG) --cflags --libs gtk+-3.0 gio-unix-2.0)
endef

define Package/openwrt-desktop-launcher/install
	$(INSTALL_DIR) $(1)/usr/bin $(1)/usr/share/applications $(1)/usr/share/icons/hicolor/scalable/apps
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/desktop-applications $(1)/usr/bin/
	$(INSTALL_DATA) ./files/*.desktop $(1)/usr/share/applications/
	$(INSTALL_DATA) ./files/desktop-applications.svg $(1)/usr/share/icons/hicolor/scalable/apps/
	$(INSTALL_DIR) $(1)/usr/share/icons/hicolor/32x32/apps
	$(INSTALL_DATA) ./files/desktop-applications.png $(1)/usr/share/icons/hicolor/32x32/apps/
endef

$(eval $(call BuildPackage,openwrt-desktop-launcher))
