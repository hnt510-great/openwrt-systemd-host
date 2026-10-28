include $(TOPDIR)/rules.mk

PKG_NAME:=openwrt-desktop-ime
PKG_VERSION:=1
PKG_RELEASE:=4
PKG_LICENSE:=MIT

include $(INCLUDE_DIR)/package.mk

define Package/openwrt-desktop-ime
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Chinese Pinyin for the shared GNOME desktop
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +openwrt-desktop +fcitx5-chinese-addons +fcitx5-gtk +gnome-shell-extension-kimpanel +noto-sans-cjk-sc
endef

define Build/Compile
endef

define Package/openwrt-desktop-ime/install
	$(INSTALL_DIR) $(1)/usr/libexec $(1)/usr/share/openwrt-desktop-ime
	$(INSTALL_BIN) ./files/desktop-ime-session $(1)/usr/libexec/
	$(INSTALL_DATA) ./files/config ./files/profile ./files/classicui.conf $(1)/usr/share/openwrt-desktop-ime/
	$(INSTALL_DIR) $(1)/usr/lib/systemd/user
	$(INSTALL_DATA) ./files/openwrt-fcitx5.service $(1)/usr/lib/systemd/user/
endef
$(eval $(call BuildPackage,openwrt-desktop-ime))
