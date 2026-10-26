include $(TOPDIR)/rules.mk

PKG_NAME:=openwrt-desktop-ime
PKG_VERSION:=1
PKG_RELEASE:=1
PKG_LICENSE:=MIT

include $(INCLUDE_DIR)/package.mk

define Package/openwrt-desktop-ime
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Chinese Pinyin for the shared Weston and RDP desktop
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +openwrt-desktop +fcitx5-chinese-addons +fcitx5-gtk +noto-sans-cjk-sc
endef

define Build/Compile
endef

define Package/openwrt-desktop-ime/install
	$(INSTALL_DIR) $(1)/usr/libexec $(1)/usr/share/openwrt-desktop-ime
	$(INSTALL_BIN) ./files/desktop-ime-session $(1)/usr/libexec/
	$(INSTALL_DATA) ./files/config ./files/profile ./files/classicui.conf $(1)/usr/share/openwrt-desktop-ime/
endef
$(eval $(call BuildPackage,openwrt-desktop-ime))
