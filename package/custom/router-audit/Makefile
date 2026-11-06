include $(TOPDIR)/rules.mk

PKG_NAME:=router-audit
PKG_VERSION:=1.0.0
PKG_RELEASE:=4
PKG_LICENSE:=GPL-2.0-only
PKG_FILE_DEPENDS:=$(TOPDIR)/docs/router-audit.md

include $(INCLUDE_DIR)/package.mk

define Package/router-audit
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Read-only router audit export and bounded minute collection
  DEPENDS:=@OPENWRT_SYSTEMD +python3 +python3-sqlite3 +git +ubus +uci-history +ip-full +nftables-json +sudo
  PKGARCH:=all
endef

define Build/Compile
endef

define Package/router-audit/install
	$(INSTALL_DIR) $(1)/usr/libexec $(1)/usr/sbin $(1)/usr/share/router-audit $(1)/usr/share/doc/router-audit
	$(INSTALL_BIN) ./files/router-audit ./files/router-audit-read ./files/router-audit-ssh $(1)/usr/libexec/
	$(LN) /usr/libexec/router-audit-read $(1)/usr/sbin/router-audit-export
	$(INSTALL_DATA) ./files/normalize.py $(1)/usr/libexec/router-audit-normalize.py
	$(INSTALL_BIN) ./files/pull.py ./files/analyze.py ./files/explain.py ./files/mcp_server.py $(1)/usr/share/router-audit/
	$(INSTALL_DATA) ./files/normalize.py ./files/schema.json $(1)/usr/share/router-audit/
	$(INSTALL_DIR) $(1)/usr/share/router-audit/prompts
	$(INSTALL_DATA) ./files/prompts/*.txt ./files/prompts/*.json $(1)/usr/share/router-audit/prompts/
	$(INSTALL_DATA) $(TOPDIR)/docs/router-audit.md $(1)/usr/share/doc/router-audit/README.md
	$(INSTALL_DIR) $(1)/usr/lib/systemd/system $(1)/etc/systemd/system/multi-user.target.wants
	$(INSTALL_DATA) ./files/router-audit-collect.service $(1)/usr/lib/systemd/system/
	$(LN) /usr/lib/systemd/system/router-audit-collect.service $(1)/etc/systemd/system/multi-user.target.wants/
	$(INSTALL_DIR) $(1)/etc/sudoers.d $(1)/srv/router-audit
	$(INSTALL_DATA) ./files/router-audit.sudoers $(1)/etc/sudoers.d/router-audit
	chmod 0440 $(1)/etc/sudoers.d/router-audit
	chmod 0700 $(1)/srv/router-audit
endef

define Package/router-audit/postinst
#!/bin/sh
[ -z "$$IPKG_INSTROOT" ] || exit 0
mkdir -p /srv/router-audit
chmod 0700 /srv/router-audit
[ -d /run/systemd/system ] || exit 0
systemctl daemon-reload
systemctl enable --now router-audit-collect.service
exit 0
endef

define Package/router-audit/prerm
#!/bin/sh
[ -z "$$IPKG_INSTROOT" ] || exit 0
systemctl disable --now router-audit-collect.service || true
exit 0
endef

$(eval $(call BuildPackage,router-audit))
