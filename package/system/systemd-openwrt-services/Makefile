include $(TOPDIR)/rules.mk

PKG_NAME:=systemd-openwrt-services
PKG_RELEASE:=6
PKG_LICENSE:=GPL-2.0-only
PKG_BUILD_DEPENDS:=libubus libubox systemd json-c

include $(INCLUDE_DIR)/package.mk

define Package/systemd-openwrt-services
  SECTION:=base
  CATEGORY:=Base system
  TITLE:=systemctl controls for OpenWrt services
  DEPENDS:=@OPENWRT_SYSTEMD +systemd-openwrt +libsystemd +libubus +libubox +libblobmsg-json +libjson-c
endef

define Package/systemd-openwrt-services/description
  Preserve procd supervision and OpenWrt startup settings while exposing
  init-script actions and live service status through systemctl.
endef

define Build/Prepare
	$(INSTALL_DIR) $(PKG_BUILD_DIR)
	$(CP) ./src/* $(PKG_BUILD_DIR)/
endef

define Build/Compile
	$(TARGET_CC) $(TARGET_CPPFLAGS) $(TARGET_CFLAGS) -Wall -Wextra -Werror \
		-o $(PKG_BUILD_DIR)/openwrt-service-bridge $(PKG_BUILD_DIR)/service-bridge.c \
		$(TARGET_LDFLAGS) -lubus -lubox -lblobmsg_json -ljson-c -lsystemd
endef

define Package/systemd-openwrt-services/install
	$(INSTALL_DIR) $(1)/usr/libexec $(1)/usr/lib/systemd/system \
		$(1)/etc/systemd/system/multi-user.target.wants \
		$(1)/usr/share/openwrt-service-bridge
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/openwrt-service-bridge $(1)/usr/libexec/
	$(INSTALL_DATA) ./files/openwrt-service-bridge.service $(1)/usr/lib/systemd/system/
	$(INSTALL_DATA) ./files/service-kinds $(1)/usr/share/openwrt-service-bridge/
	$(LN) /usr/lib/systemd/system/openwrt-service-bridge.service \
		$(1)/etc/systemd/system/multi-user.target.wants/
endef

$(eval $(call BuildPackage,systemd-openwrt-services))
