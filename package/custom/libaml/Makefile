include $(TOPDIR)/rules.mk

PKG_NAME:=aml
PKG_VERSION:=1.0.0
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=https://codeload.github.com/any1/aml/tar.gz/v$(PKG_VERSION)?
PKG_HASH:=b2b8f743213af39f40e8bc611147d69e2ea9e010b9b19cb65246582338f28d96
PKG_LICENSE:=ISC
PKG_LICENSE_FILES:=COPYING
PKG_INSTALL:=1

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/meson.mk

define Package/libaml
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=Another main loop library
  URL:=https://github.com/any1/aml
  DEPENDS:=+libpthread
endef

MESON_ARGS += -Dexamples=false

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/include/aml1 $(1)/usr/lib/pkgconfig
	$(CP) $(PKG_INSTALL_DIR)/usr/include/aml1/*.h $(1)/usr/include/aml1/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libaml.so* $(1)/usr/lib/
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/aml1.pc $(1)/usr/lib/pkgconfig/
endef

define Package/libaml/install
	$(INSTALL_DIR) $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libaml.so* $(1)/usr/lib/
endef

$(eval $(call BuildPackage,libaml))
