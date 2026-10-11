include $(TOPDIR)/rules.mk
PKG_NAME:=libgtk3
PKG_VERSION:=3.24.52
PKG_RELEASE:=1
PKG_SOURCE:=gtk-3.24.52.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/gtk/3.24/
PKG_HASH:=80931fa472a77b9a164f6740e3c0b444fac6770054632d35a7ff9d679e5e7b9f
PKG_BUILD_DIR:=$(BUILD_DIR)/gtk-$(PKG_VERSION)
PKG_LICENSE:=LGPL-2.1-or-later
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=glib2/host libxml2/host wayland/host wayland-protocols
include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/meson.mk
include $(INCLUDE_DIR)/gobject-introspection.mk

define Package/libgtk3
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=libgtk3
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +glib2-gir +glib2-utils +at-spi2-core +libpango +libgdk-pixbuf +libcairo +libepoxy +libwayland +libxkbcommon +libmesa +libjpeg +libpng +libtiff +fontconfig +libintl-full +adwaita-icons
endef
MESON_ARGS += -Dintrospection=true -Dx11_backend=false -Dwayland_backend=true -Dbroadway_backend=false -Dquartz_backend=false -Dwin32_backend=false -Dprint_backends=file -Dcolord=no -Dgtk_doc=false -Dman=false -Ddemos=false -Dexamples=false -Dtests=false -Dinstalled_tests=false

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/lib $(1)/usr/include $(1)/usr/share/gir-1.0 $(1)/usr/lib/girepository-1.0
	[ ! -d $(PKG_INSTALL_DIR)/usr/include ] || $(CP) $(PKG_INSTALL_DIR)/usr/include/. $(1)/usr/include/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so* $(1)/usr/lib/
	[ ! -d $(PKG_INSTALL_DIR)/usr/lib/pkgconfig ] || $(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig $(1)/usr/lib/
	[ ! -d $(PKG_INSTALL_DIR)/usr/share/gir-1.0 ] || $(CP) $(PKG_INSTALL_DIR)/usr/share/gir-1.0/. $(1)/usr/share/gir-1.0/
	[ ! -d $(PKG_INSTALL_DIR)/usr/lib/girepository-1.0 ] || $(CP) $(PKG_INSTALL_DIR)/usr/lib/girepository-1.0/. $(1)/usr/lib/girepository-1.0/
endef

define Package/libgtk3/install
	$(INSTALL_DIR) $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so* $(1)/usr/lib/
	[ ! -d $(PKG_INSTALL_DIR)/usr/lib/girepository-1.0 ] || $(CP) $(PKG_INSTALL_DIR)/usr/lib/girepository-1.0 $(1)/usr/lib/
	$(INSTALL_DIR) $(1)/usr/share
	$(CP) $(PKG_INSTALL_DIR)/usr/share/glib-2.0 $(1)/usr/share/
	$(CP) $(PKG_INSTALL_DIR)/usr/share/themes $(1)/usr/share/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/gtk-3.0 $(1)/usr/lib/
endef

define Package/libgtk3/postinst
#!/bin/sh
[ -n "$$IPKG_INSTROOT" ] || /usr/libexec/glib2-cache-update
exit 0
endef
$(eval $(call BuildPackage,libgtk3))
