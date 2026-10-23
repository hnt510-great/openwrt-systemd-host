include $(TOPDIR)/rules.mk

PKG_NAME:=openwrt-flatpak
PKG_VERSION:=1
PKG_RELEASE:=7
PKG_LICENSE:=MIT

include $(INCLUDE_DIR)/package.mk

define Package/openwrt-flatpak
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Ordinary-user Flatpak integration for Weston
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC @OPENWRT_SYSTEMD +flatpak +xdg-desktop-portal-gtk +openwrt-desktop
endef

define Build/Compile
	$(TARGET_CC) $(TARGET_CFLAGS) $(TARGET_CPPFLAGS) -Wall -Wextra \
		-o $(PKG_BUILD_DIR)/desktop-no-caps ./src/desktop-no-caps.c $(TARGET_LDFLAGS)
endef

define Package/openwrt-flatpak/install
	$(INSTALL_DIR) $(1)/usr/sbin $(1)/usr/libexec $(1)/usr/share/xdg-desktop-portal
	$(INSTALL_BIN) ./files/flatpak-user-setup $(1)/usr/sbin/
	$(INSTALL_BIN) ./files/flatpak-user-link $(1)/usr/libexec/
	$(INSTALL_BIN) ./files/desktop-flatpak-session $(1)/usr/libexec/
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/desktop-no-caps $(1)/usr/libexec/
	$(INSTALL_DATA) ./files/weston-portals.conf $(1)/usr/share/xdg-desktop-portal/
	$(INSTALL_DIR) $(1)/etc/udev/rules.d
	$(INSTALL_DATA) ./files/99-flatpak-fuse.rules $(1)/etc/udev/rules.d/
	$(INSTALL_DIR) $(1)/etc/hotplug.json.d $(1)/usr/lib/systemd/user
	$(INSTALL_DATA) ./files/flatpak-fuse.json $(1)/etc/hotplug.json.d/
	$(INSTALL_DATA) ./files/openwrt-flatpak-session.target $(1)/usr/lib/systemd/user/
endef

$(eval $(call BuildPackage,openwrt-flatpak))
