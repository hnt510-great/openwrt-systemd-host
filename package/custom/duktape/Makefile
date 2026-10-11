include $(TOPDIR)/rules.mk

PKG_NAME:=duktape
PKG_VERSION:=2.7.0
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://duktape.org/
PKG_HASH:=90f8d2fa8b5567c6899830ddef2c03f3c27960b11aca222fa17aa7ac613c2890
PKG_LICENSE:=MIT
PKG_LICENSE_FILES:=LICENSE.txt

include $(INCLUDE_DIR)/package.mk

define Package/libduktape
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=Duktape JavaScript engine library
  URL:=https://duktape.org/
endef

define Build/Configure
endef

define Build/Compile
	$(TARGET_CC) $(TARGET_CPPFLAGS) $(TARGET_CFLAGS) -fPIC -shared \
		-Wl,-soname,libduktape.so.207 $(TARGET_LDFLAGS) \
		-o $(PKG_BUILD_DIR)/libduktape.so.207 $(PKG_BUILD_DIR)/src/duktape.c -lm
endef

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/lib/pkgconfig $(1)/usr/include
	$(CP) $(PKG_BUILD_DIR)/src/duktape.h $(PKG_BUILD_DIR)/src/duk_config.h $(1)/usr/include/
	$(CP) $(PKG_BUILD_DIR)/libduktape.so.207 $(1)/usr/lib/
	$(LN) libduktape.so.207 $(1)/usr/lib/libduktape.so
	sed -e 's|@PREFIX@|/usr|g' -e 's|@LIBDIR@|/lib|g' \
		-e 's|@VERSION@|$(PKG_VERSION)|g' $(PKG_BUILD_DIR)/duktape.pc.in \
		> $(1)/usr/lib/pkgconfig/duktape.pc
endef

define Package/libduktape/install
	$(INSTALL_DIR) $(1)/usr/lib
	$(CP) $(PKG_BUILD_DIR)/libduktape.so.207 $(1)/usr/lib/
endef

$(eval $(call BuildPackage,libduktape))
