include $(TOPDIR)/rules.mk

PKG_NAME:=iso-codes
PKG_VERSION:=4.18.0
PKG_RELEASE:=2
PKG_SOURCE:=iso-codes_$(PKG_VERSION).orig.tar.xz
PKG_SOURCE_URL:=https://deb.debian.org/debian/pool/main/i/iso-codes/
PKG_HASH:=066bc4df7bf299561856a07119cde01d563c8c4c39906537a39363bb833d466c
PKG_LICENSE:=LGPL-2.1-or-later
PKG_INSTALL:=
PKG_BUILD_DEPENDS:=python3/host

include $(INCLUDE_DIR)/package.mk

define Package/iso-codes
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=ISO language names for input methods
  PKGARCH:=all
endef

define Build/Configure
endef

define Build/Compile
	$(STAGING_DIR_HOSTPKG)/bin/python3 ./files/legacy-xml.py $(PKG_BUILD_DIR)/data $(PKG_BUILD_DIR)/legacy-xml
endef

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/share/iso-codes/json
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/data/*.json $(1)/usr/share/iso-codes/json/
	$(INSTALL_DIR) $(1)/usr/share/xml/iso-codes $(1)/usr/share/pkgconfig
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/legacy-xml/*.xml $(1)/usr/share/xml/iso-codes/
	$(STAGING_DIR_HOST)/bin/sed -e 's|@prefix@|/usr|g' -e 's|@VERSION@|$(PKG_VERSION)|g' \
		-e 's|@DOMAINS@|iso_639 iso_639_3 iso_3166|g' \
		$(PKG_BUILD_DIR)/iso-codes.pc.in > $(1)/usr/share/pkgconfig/iso-codes.pc
endef

define Package/iso-codes/install
	$(call Build/InstallDev,$(1))
endef
$(eval $(call BuildPackage,iso-codes))
