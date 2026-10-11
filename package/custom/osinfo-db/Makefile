include $(TOPDIR)/rules.mk
PKG_NAME:=osinfo-db
PKG_VERSION:=20251212
PKG_RELEASE:=1
PKG_SOURCE:=osinfo-db-20251212.tar.xz
PKG_SOURCE_URL:=https://releases.pagure.org/libosinfo/
PKG_HASH:=06379250c91306c98cb9726af44eae5909dfdd5449f90331e904ae1221d8d5e7
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
