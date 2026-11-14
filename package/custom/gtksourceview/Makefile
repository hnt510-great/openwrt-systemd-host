include $(TOPDIR)/rules.mk

PKG_NAME:=gtksourceview
PKG_VERSION:=5.22.0
PKG_RELEASE:=1
PKG_SOURCE:=gtksourceview-5.22.0.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/gtksourceview/5.22/
PKG_HASH:=3ebce33c781e65590a450ecd3ffade480d8e3135b52ee996f1620d6c7dffbbff
PKG_LICENSE:=LGPL-2.1-or-later
PKG_LICENSE_FILES:=COPYING
PKG_BUILD_DEPENDS:=vala/host libxml2/host
GNOME_TITLE:=GTK4 source code editing widget
GNOME_DEPENDS:=+glib2-gir +gtk4 +libxml2 +fribidi +fontconfig +libpango +libpcre2
GNOME_MESON_ARGS:=-Dintrospection=enabled -Dvapi=true -Ddocumentation=false -Dsysprof=false -Dbuild-testsuite=false -Dinstall-tests=false

include $(INCLUDE_DIR)/gnome-package.mk

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/include $(1)/usr/lib $(1)/usr/share
	[ ! -d $(PKG_INSTALL_DIR)/usr/include ] || $(CP) $(PKG_INSTALL_DIR)/usr/include/. $(1)/usr/include/
	[ ! -d $(PKG_INSTALL_DIR)/usr/lib ] || $(CP) $(PKG_INSTALL_DIR)/usr/lib/. $(1)/usr/lib/
	for dir in pkgconfig gir-1.0 glib-2.0 vala; do \
		[ ! -d $(PKG_INSTALL_DIR)/usr/share/$$$$dir ] || $(CP) $(PKG_INSTALL_DIR)/usr/share/$$$$dir $(1)/usr/share/; \
	done
endef

define Package/gtksourceview/install
	[ ! -d $(PKG_INSTALL_DIR)/usr ] || $(CP) $(PKG_INSTALL_DIR)/usr $(1)/
	$(RM) -r $(1)/usr/include $(1)/usr/lib/pkgconfig $(1)/usr/share/pkgconfig \
		$(1)/usr/share/gir-1.0 $(1)/usr/share/vala $(1)/usr/share/gtk-doc $(1)/usr/share/doc $(1)/usr/share/man
	find $(1) -type f \( -name '*.a' -o -name '*.la' \) -delete
endef

$(eval $(call BuildPackage,$(PKG_NAME)))
