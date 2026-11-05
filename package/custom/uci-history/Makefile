include $(TOPDIR)/rules.mk

PKG_NAME:=uci-history
PKG_VERSION:=1.0.0
PKG_RELEASE:=2
PKG_LICENSE:=GPL-2.0-only

include $(INCLUDE_DIR)/package.mk

define Package/uci-history
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Transactional UCI configuration revision history
  DEPENDS:=@OPENWRT_SYSTEMD +python3 +git +ubus
  PKGARCH:=all
endef

define Package/uci-history/conffiles
/etc/config/uci-history
endef

define Build/Compile
endef

define Package/uci-history/install
	$(INSTALL_DIR) $(1)/usr/sbin $(1)/etc/config $(1)/lib/apk/commit_hooks.d \
		$(1)/lib/upgrade/keep.d $(1)/usr/share/doc/uci-history \
		$(1)/usr/lib/systemd/system $(1)/etc/systemd/system/multi-user.target.wants
	$(INSTALL_BIN) ./files/uci-history $(1)/usr/sbin/
	$(INSTALL_CONF) ./files/uci-history.config $(1)/etc/config/uci-history
	$(INSTALL_BIN) ./files/apk.hook $(1)/lib/apk/commit_hooks.d/80-uci-history
	$(INSTALL_DATA) ./files/keep.d $(1)/lib/upgrade/keep.d/uci-history
	$(INSTALL_DATA) ./files/AGENT-GUIDE.md $(1)/usr/share/doc/uci-history/
	$(INSTALL_DATA) ./files/*.service ./files/*.path ./files/*.timer $(1)/usr/lib/systemd/system/
	$(foreach unit,uci-history.path uci-history-sweep.timer uci-history-events.service uci-history-boot.service,$(LN) /usr/lib/systemd/system/$(unit) $(1)/etc/systemd/system/multi-user.target.wants/;)
endef

define Package/uci-history/postinst
#!/bin/sh
[ -z "$$IPKG_INSTROOT" ] || exit 0
[ -d /run/systemd/system ] || exit 0
systemctl daemon-reload
systemctl start uci-history-boot.service uci-history.path uci-history-sweep.timer uci-history-events.service || true
exit 0
endef

define Package/uci-history/prerm
#!/bin/sh
[ -z "$$IPKG_INSTROOT" ] || exit 0
[ -d /run/systemd/system ] || exit 0
# Resolve the persistent safety marker before removing the executable.
if [ -f /etc/uci-history/txn.json ]; then
	/usr/sbin/uci-history --json abort || exit 1
fi
systemctl stop uci-history.path uci-history-sweep.timer uci-history-events.service uci-history-snapshot.service uci-history-boot.service || true
exit 0
endef

$(eval $(call BuildPackage,uci-history))
