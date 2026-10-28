include $(TOPDIR)/rules.mk

PKG_NAME:=gobject-introspection
PKG_VERSION:=1.86.0
PKG_RELEASE:=3
PKG_SOURCE:=gobject-introspection-1.86.0.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/gobject-introspection/1.86/
PKG_HASH:=920d1a3fcedeadc32acff95c2e203b319039dd4b4a08dd1a2dfd283d19c0b9ae
PKG_LICENSE:=LGPL-2.0-or-later
PKG_INSTALL:=1
HOST_BUILD_DEPENDS:=glib2/host libffi/host python3/host python-setuptools/host
HOST_BUILD_PARALLEL:=1
OPAQUE_TYPELIBS:=xlib-2.0 xfixes-4.0 GL-1.0 DBus-1.0
PKG_BUILD_DEPENDS:=gobject-introspection/host

include $(INCLUDE_DIR)/host-build.mk
include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/meson.mk
include $(TOPDIR)/feeds/packages/lang/python/python3-host.mk

MESON_USE_STAGING_PYTHON:=1
PYTHON_BIN:=$(STAGING_DIR_HOSTPKG)/bin/python3
MESON_HOST_ARGS += -Dpython=$(HOST_PYTHON3_BIN) -Dtests=false -Ddoctool=disabled -Dcairo=disabled -Dbuild_introspection_data=false

define Package/gobject-introspection
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=GObject introspection base metadata
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +libcairo
endef

define Build/Configure
endef

define Build/Compile
	$(CP) $(PKG_BUILD_DIR)/gir/cairo-1.0.gir.in $(PKG_BUILD_DIR)/gir/cairo-1.0.gir
	$(SED) 's|@CAIRO_SHARED_LIBRARY@|libcairo-gobject.so.2|g;s|@CAIRO_GIR_PACKAGE@|cairo-gobject|g' $(PKG_BUILD_DIR)/gir/cairo-1.0.gir
	# GTK, Mutter and AT-SPI import these namespaces at runtime, even though
	# their C types are opaque. Generate data without loading target libraries.
	for ns in $(OPAQUE_TYPELIBS); do \
		$(STAGING_DIR_HOSTPKG)/bin/g-ir-compiler $(PKG_BUILD_DIR)/gir/$$$$ns.gir \
			-o $(PKG_BUILD_DIR)/gir/$$$$ns.typelib || exit 1; \
	done
endef

define Build/Install
endef

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/share/gir-1.0 $(1)/usr/lib/pkgconfig $(1)/usr/bin $(1)/usr/lib/girepository-1.0
	$(CP) $(PKG_BUILD_DIR)/gir/*.gir $(1)/usr/share/gir-1.0/
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/gir/*.typelib $(1)/usr/lib/girepository-1.0/
	$(INSTALL_BIN) ./files/g-ir-scanner $(1)/usr/bin/g-ir-scanner
	$(SED) 's|@HOSTPKG@|$(STAGING_DIR_HOSTPKG)|g;s|@TOPDIR@|$(TOPDIR)|g;s|@STAGING@|$(STAGING_DIR)|g' $(1)/usr/bin/g-ir-scanner
	$(INSTALL_BIN) ./files/g-ir-compiler $(1)/usr/bin/g-ir-compiler
	$(SED) 's|@HOSTPKG@|$(STAGING_DIR_HOSTPKG)|g;s|@STAGING@|$(STAGING_DIR)|g' $(1)/usr/bin/g-ir-compiler
	$(INSTALL_DATA) ./files/gobject-introspection-1.0.pc $(1)/usr/lib/pkgconfig/
	$(SED) 's|@STAGING@|$(STAGING_DIR)|g;s|@HOSTPKG@|$(STAGING_DIR_HOSTPKG)|g;s|@VERSION@|$(PKG_VERSION)|g' $(1)/usr/lib/pkgconfig/gobject-introspection-1.0.pc
	$(INSTALL_DIR) $(1)/usr/share/gobject-introspection-1.0
	$(INSTALL_DATA) $(STAGING_DIR_HOSTPKG)/share/gobject-introspection-1.0/Makefile.introspection $(1)/usr/share/gobject-introspection-1.0/
endef

define Package/gobject-introspection/install
	$(INSTALL_DIR) $(1)/usr/lib/girepository-1.0
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/gir/*.typelib $(1)/usr/lib/girepository-1.0/
endef

$(eval $(call HostBuild))
$(eval $(call BuildPackage,gobject-introspection))
