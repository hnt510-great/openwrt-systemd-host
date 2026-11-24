include $(TOPDIR)/rules.mk

PKG_NAME:=openwrt-desktop-ime
PKG_VERSION:=1
PKG_RELEASE:=8
PKG_LICENSE:=MIT

include $(INCLUDE_DIR)/package.mk

define Package/openwrt-desktop-ime-base
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Fcitx5 and Chinese Pinyin base for the desktop
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +openwrt-desktop-base +fcitx5-chinese-addons +fcitx5-gtk +noto-sans-cjk-sc
endef

define Package/openwrt-desktop-ime
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Chinese Pinyin for the shared GNOME desktop
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +openwrt-desktop-ime-base +openwrt-desktop-core +gnome-shell-extension-kimpanel
endef

define Package/openwrt-desktop-ime-plasma
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Chinese Pinyin for the shared KDE Plasma desktop
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +openwrt-desktop-ime-base +fcitx5-qt
endef

define Build/Compile
endef

define Package/openwrt-desktop-ime-base/install
	$(INSTALL_DIR) $(1)/usr/libexec $(1)/usr/share/openwrt-desktop-ime
	$(INSTALL_BIN) ./files/desktop-ime-init ./files/desktop-ime-session $(1)/usr/libexec/
	$(INSTALL_DATA) ./files/config ./files/profile ./files/classicui.conf $(1)/usr/share/openwrt-desktop-ime/
endef

define Package/openwrt-desktop-ime/install
	$(INSTALL_DIR) $(1)/usr/lib/systemd/user
	$(INSTALL_DATA) ./files/openwrt-fcitx5.service $(1)/usr/lib/systemd/user/
endef

define Package/openwrt-desktop-ime-plasma/install
	$(INSTALL_DIR) $(1)/usr/lib/systemd/user
	$(INSTALL_DATA) ./files/openwrt-fcitx5-plasma.service $(1)/usr/lib/systemd/user/
endef

$(eval $(call BuildPackage,openwrt-desktop-ime-base))
$(eval $(call BuildPackage,openwrt-desktop-ime))
$(eval $(call BuildPackage,openwrt-desktop-ime-plasma))
