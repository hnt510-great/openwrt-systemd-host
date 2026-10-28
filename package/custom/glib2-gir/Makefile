include $(TOPDIR)/rules.mk
PKG_NAME:=glib2-gir
PKG_VERSION:=2.90.1
PKG_RELEASE:=1
PKG_SOURCE:=glib-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=@GNOME/glib/2.90
PKG_HASH:=93c941aa17d5eb1d53fe838365f29a8b4e539c222a256d974ec8f30fc413e396
PKG_BUILD_DIR:=$(BUILD_DIR)/glib-gir-$(PKG_VERSION)
PKG_UNPACK:=mkdir -p $(PKG_BUILD_DIR); xzcat $(DL_DIR)/$(PKG_SOURCE) | $(TAR) --strip-components=1 -C $(PKG_BUILD_DIR) -xf -
PKG_LICENSE:=LGPL-2.1-or-later
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=glib2/host
include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/meson.mk
include $(INCLUDE_DIR)/gobject-introspection.mk

define Package/glib2-gir
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=GLib GObject and Gio introspection metadata
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +glib2 +libgirepository2 +gobject-introspection +libcairo +libxml2
endef
MESON_ARGS += -Dintrospection=enabled -Dtests=false -Dlibmount=disabled -Dselinux=disabled -Dlibelf=disabled -Dnls=disabled

define Build/Install
	$(call Build/Install/Meson)
	for ns in cairo-1.0 libxml2-2.0 freetype2-2.0 fontconfig-2.0; do \
		$(STAGING_DIR)/usr/bin/g-ir-compiler --includedir=$(PKG_INSTALL_DIR)/usr/share/gir-1.0 \
			$(STAGING_DIR)/usr/share/gir-1.0/$$$$ns.gir -o $(PKG_INSTALL_DIR)/usr/lib/girepository-1.0/$$$$ns.typelib || exit 1; \
	done
endef

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/share/gir-1.0 $(1)/usr/lib/girepository-1.0
	$(CP) $(PKG_INSTALL_DIR)/usr/share/gir-1.0/*.gir $(1)/usr/share/gir-1.0/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/girepository-1.0/*.typelib $(1)/usr/lib/girepository-1.0/
endef

define Package/glib2-gir/install
	$(INSTALL_DIR) $(1)/usr/lib/girepository-1.0
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/girepository-1.0/*.typelib $(1)/usr/lib/girepository-1.0/
endef
$(eval $(call BuildPackage,glib2-gir))
