include $(TOPDIR)/rules.mk

PKG_NAME:=openwrt-podman-rootless
PKG_RELEASE:=4
PKG_LICENSE:=GPL-2.0-only

include $(INCLUDE_DIR)/package.mk

define Package/openwrt-podman-rootless
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=OpenWrt rootless Podman account setup
  DEPENDS:=+podman +shadow-usermod +shadow-groupadd +fuse-overlayfs \
	+OPENWRT_SYSTEMD:shadow-su +OPENWRT_SYSTEMD:acl
endef

define Build/Compile
endef

define Package/openwrt-podman-rootless/install
	$(INSTALL_DIR) $(1)/usr/sbin $(1)/usr/libexec $(1)/etc/init.d
	$(INSTALL_DIR) $(1)/etc/uci-defaults $(1)/etc/modules-boot.d
	$(INSTALL_BIN) ./files/podman-rootless-setup $(1)/usr/sbin/
	$(INSTALL_BIN) ./files/podman-tun-permissions $(1)/usr/libexec/
	$(INSTALL_BIN) ./files/podman-native-storage $(1)/usr/libexec/
	$(INSTALL_BIN) ./files/podman-rootless.init $(1)/etc/init.d/podman-rootless
	$(INSTALL_BIN) ./files/podman-rootless.defaults $(1)/etc/uci-defaults/99-podman-rootless
	$(INSTALL_DATA) ./files/30-podman-tun $(1)/etc/modules-boot.d/
endef

$(eval $(call BuildPackage,openwrt-podman-rootless))
