include $(TOPDIR)/rules.mk
PKG_NAME:=osinfo-db
PKG_VERSION:=20260812
PKG_RELEASE:=1
PKG_SOURCE:=osinfo-db-20260812.tar.xz
PKG_SOURCE_URL:=https://gitlab.com/libosinfo/osinfo-db/-/releases/v20260812/downloads/
PKG_HASH:=f13ed6e1e480b5266d39cad7f0010febdf0265dfc45579de2fb34543bc6b35de
PKG_LICENSE:=GPL-2.0-or-later
include $(INCLUDE_DIR)/package.mk
define Package/osinfo-db
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=Operating system metadata database
endef
define Build/Compile
endef
define Package/osinfo-db/install
	$(INSTALL_DIR) $(1)/usr/share/osinfo
	$(foreach dir,datamap device install-script os platform schema,$(CP) $(PKG_BUILD_DIR)/$(dir) $(1)/usr/share/osinfo/;)
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/LICENSE $(PKG_BUILD_DIR)/VERSION $(1)/usr/share/osinfo/
endef
$(eval $(call BuildPackage,osinfo-db))
