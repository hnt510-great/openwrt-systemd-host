include $(TOPDIR)/rules.mk

PKG_NAME:=libpwquality
PKG_VERSION:=1.4.5
PKG_RELEASE:=1
PKG_SOURCE:=libpwquality-1.4.5.tar.bz2
PKG_SOURCE_URL:=https://github.com/libpwquality/libpwquality/releases/download/libpwquality-1.4.5/
PKG_HASH:=6fcf18b75d305d99d04d2e42982ed5b787a081af2842220ed63287a2d6a10988
PKG_BUILD_DIR:=$(BUILD_DIR)/libpwquality-$(PKG_VERSION)
PKG_LICENSE:=LGPL-2.1-or-later
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=glib2/host gobject-introspection/host gobject-introspection

include $(INCLUDE_DIR)/package.mk

define Package/libpwquality
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=libpwquality GNOME Settings library
  DEPENDS:=+libpam
endef

CONFIGURE_ARGS += --disable-python-bindings --disable-cracklib-check
CONFIGURE_VARS += GI_CROSS_LAUNCHER="$(TOPDIR)/scripts/gi-target-runner" \
	GI_SCANNER="$(STAGING_DIR)/usr/bin/g-ir-scanner" GI_COMPILER="$(STAGING_DIR)/usr/bin/g-ir-compiler"

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/include $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/include/. $(1)/usr/include/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/. $(1)/usr/lib/
	[ ! -d $(PKG_INSTALL_DIR)/usr/share/gir-1.0 ] || $(CP) $(PKG_INSTALL_DIR)/usr/share/gir-1.0 $(1)/usr/share/
endef

define Package/libpwquality/install
	$(CP) $(PKG_INSTALL_DIR)/usr $(1)/
	[ ! -d $(PKG_INSTALL_DIR)/etc ] || $(CP) $(PKG_INSTALL_DIR)/etc $(1)/
	$(RM) -r $(1)/usr/include $(1)/usr/lib/pkgconfig $(1)/usr/share/gir-1.0 $(1)/usr/share/gtk-doc $(1)/usr/share/man
	find $(1) -type f \( -name '*.a' -o -name '*.la' \) -delete
endef

$(eval $(call BuildPackage,libpwquality))
