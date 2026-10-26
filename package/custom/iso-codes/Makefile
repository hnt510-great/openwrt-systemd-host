include $(TOPDIR)/rules.mk

PKG_NAME:=iso-codes
PKG_VERSION:=4.18.0
PKG_RELEASE:=1
PKG_SOURCE:=iso-codes_$(PKG_VERSION).orig.tar.xz
PKG_SOURCE_URL:=https://deb.debian.org/debian/pool/main/i/iso-codes/
PKG_HASH:=066bc4df7bf299561856a07119cde01d563c8c4c39906537a39363bb833d466c
PKG_LICENSE:=LGPL-2.1-or-later
PKG_INSTALL:=

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
endef

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/share/iso-codes/json
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/data/iso_639-3.json $(1)/usr/share/iso-codes/json/
endef

define Package/iso-codes/install
	$(call Build/InstallDev,$(1))
endef
$(eval $(call BuildPackage,iso-codes))
