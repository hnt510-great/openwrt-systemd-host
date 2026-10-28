include $(TOPDIR)/rules.mk

PKG_NAME:=libgtop
PKG_VERSION:=2.41.3
PKG_RELEASE:=1
PKG_SOURCE:=libgtop-2.41.3.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/libgtop/2.41/
PKG_HASH:=775676df958e2ea2452f7568f28b2ea581063d312773dd5c0b7624c1b9b2da8c
PKG_BUILD_DIR:=$(BUILD_DIR)/libgtop-$(PKG_VERSION)
PKG_LICENSE:=GPL-2.0-or-later
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=glib2/host gobject-introspection/host gobject-introspection

include $(INCLUDE_DIR)/package.mk

define Package/libgtop
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=libgtop GNOME Settings library
  DEPENDS:=+glib2 +libXau
endef

CONFIGURE_ARGS += --disable-introspection --without-x
CONFIGURE_VARS += GI_CROSS_LAUNCHER="$(TOPDIR)/scripts/gi-target-runner" \
	GI_SCANNER="$(STAGING_DIR)/usr/bin/g-ir-scanner" GI_COMPILER="$(STAGING_DIR)/usr/bin/g-ir-compiler"

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/include $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/include/. $(1)/usr/include/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/. $(1)/usr/lib/
	[ ! -d $(PKG_INSTALL_DIR)/usr/share/gir-1.0 ] || $(CP) $(PKG_INSTALL_DIR)/usr/share/gir-1.0 $(1)/usr/share/
endef

define Package/libgtop/install
	$(CP) $(PKG_INSTALL_DIR)/usr $(1)/
	[ ! -d $(PKG_INSTALL_DIR)/etc ] || $(CP) $(PKG_INSTALL_DIR)/etc $(1)/
	$(RM) -r $(1)/usr/include $(1)/usr/lib/pkgconfig $(1)/usr/share/gir-1.0 $(1)/usr/share/gtk-doc $(1)/usr/share/man
	find $(1) -type f \( -name '*.a' -o -name '*.la' \) -delete
endef

$(eval $(call BuildPackage,libgtop))
