include $(TOPDIR)/rules.mk

PKG_NAME:=apk-transaction-guard
PKG_VERSION:=1
PKG_RELEASE:=1
PKG_LICENSE:=GPL-2.0-only

include $(INCLUDE_DIR)/package.mk

define Package/apk-transaction-guard
  SECTION:=base
  CATEGORY:=Base system
  TITLE:=Finish interrupted APK transactions at boot
  DEPENDS:=@USE_APK
  EXTRA_DEPENDS:=apk (>=3.0.5-r18)
endef

define Package/apk-transaction-guard/description
  Boot-time recovery for APK transactions cut off by power loss, a crash or
  SIGKILL: apk-resume replays the patched APK's transaction journal, offline
  when the journal keeps the package payloads. On systemd, a pre-commit hook
  also moves each commit into its own scope and blocks ordinary shutdown
  until the package database is written.
endef

define Build/Compile
endef

define Package/apk-transaction-guard/install
	$(INSTALL_DIR) $(1)/usr/sbin $(1)/etc/init.d $(1)/lib/apk/commit_hooks.d
	$(INSTALL_BIN) ./files/apk-resume $(1)/usr/sbin/apk-resume
	$(INSTALL_BIN) ./files/apk-resume.init $(1)/etc/init.d/apk-resume
	$(INSTALL_BIN) ./files/transaction-scope.hook $(1)/lib/apk/commit_hooks.d/00-transaction-scope
	$(INSTALL_DIR) $(1)/usr/lib/systemd/system $(1)/etc/systemd/system/multi-user.target.wants
	$(INSTALL_DATA) ./files/apk-resume.service $(1)/usr/lib/systemd/system/
	$(LN) /usr/lib/systemd/system/apk-resume.service $(1)/etc/systemd/system/multi-user.target.wants/
endef

$(eval $(call BuildPackage,apk-transaction-guard))
