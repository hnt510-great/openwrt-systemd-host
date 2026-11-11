include $(TOPDIR)/rules.mk

PKG_NAME:=openwrt-needrestart
PKG_VERSION:=1.0.0
PKG_RELEASE:=13
PKG_LICENSE:=GPL-2.0-only
PKG_BUILD_DEPENDS:=libubus libubox systemd json-c

include $(INCLUDE_DIR)/package.mk

define Package/openwrt-needrestart
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Report services using obsolete executable code
  DEPENDS:=@OPENWRT_SYSTEMD @USE_APK +libsystemd +libubus +libubox +libblobmsg-json +libjson-c
endef

define Package/openwrt-needrestart/description
  Read-only restart advice for native and procd services, kernel trials, and
  rootful/rootless Podman containers. No automatic restarts or registry access.
endef

define Build/Prepare
	$(INSTALL_DIR) $(PKG_BUILD_DIR)
	$(CP) ./src/* $(PKG_BUILD_DIR)/
endef

define Build/Compile
	$(TARGET_CC) $(TARGET_CPPFLAGS) $(TARGET_CFLAGS) -Wall -Wextra -Werror \
		-o $(PKG_BUILD_DIR)/needrestart $(PKG_BUILD_DIR)/needrestart.c \
		$(TARGET_LDFLAGS) -lubus -lubox -lblobmsg_json -ljson-c -lsystemd
endef

define Package/openwrt-needrestart/install
	$(INSTALL_DIR) $(1)/usr/sbin $(1)/lib/apk/commit_hooks.d \
		$(1)/usr/lib/systemd/system $(1)/usr/lib/tmpfiles.d \
		$(1)/etc/systemd/system/multi-user.target.wants
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/needrestart $(1)/usr/sbin/
	$(INSTALL_BIN) ./files/needrestart.hook $(1)/lib/apk/commit_hooks.d/90-needrestart
	$(INSTALL_DATA) ./files/openwrt-needrestart.service $(1)/usr/lib/systemd/system/
	$(INSTALL_DATA) ./files/openwrt-needrestart.path $(1)/usr/lib/systemd/system/
	$(INSTALL_DATA) ./files/openwrt-needrestart.conf $(1)/usr/lib/tmpfiles.d/
	$(LN) /usr/lib/systemd/system/openwrt-needrestart.path \
		$(1)/etc/systemd/system/multi-user.target.wants/
endef

define Package/openwrt-needrestart/postinst
#!/bin/sh
[ -z "$$IPKG_INSTROOT" ] || exit 0
[ -d /run/systemd/system ] || exit 0
systemctl daemon-reload
systemctl start openwrt-needrestart.path || true
exit 0
endef

define Package/openwrt-needrestart/prerm
#!/bin/sh
[ -z "$$IPKG_INSTROOT" ] || exit 0
[ -d /run/systemd/system ] || exit 0
systemctl stop openwrt-needrestart.path || true
systemctl stop openwrt-needrestart.service || true
exit 0
endef

$(eval $(call BuildPackage,openwrt-needrestart))
