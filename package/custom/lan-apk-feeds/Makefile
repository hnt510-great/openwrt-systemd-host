include $(TOPDIR)/rules.mk

PKG_NAME:=lan-apk-feeds
PKG_RELEASE:=1
PKG_LICENSE:=MIT

include $(INCLUDE_DIR)/package.mk

define Package/lan-apk-feeds
  SECTION:=base
  CATEGORY:=Base system
  TITLE:=Automatic installed-kernel LAN APK feed selection
  DEPENDS:=@USE_APK
endef

define Package/lan-apk-feeds/description
  Regenerate local repository URLs from the installed kernel APK version at
  boot and after package transactions. No network access or package upgrades.
endef

define Package/lan-apk-feeds/conffiles
/etc/lan-apk-feeds.conf
endef

define Build/Compile
endef

define Package/lan-apk-feeds/install
	$(INSTALL_DIR) $(1)/etc/init.d $(1)/usr/sbin $(1)/lib/apk/commit_hooks.d
	$(INSTALL_DATA) ./files/lan-apk-feeds.conf $(1)/etc/lan-apk-feeds.conf
	$(INSTALL_BIN) ./files/lan-apk-feeds.init $(1)/etc/init.d/lan-apk-feeds
	$(INSTALL_BIN) ./files/lan-apk-feeds-sync $(1)/usr/sbin/lan-apk-feeds-sync
	$(INSTALL_BIN) ./files/lan-apk-feeds.hook $(1)/lib/apk/commit_hooks.d/30-lan-apk-feeds
endef

$(eval $(call BuildPackage,lan-apk-feeds))
