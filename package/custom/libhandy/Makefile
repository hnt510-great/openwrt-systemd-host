include $(TOPDIR)/rules.mk

PKG_NAME:=libhandy
PKG_VERSION:=1.8.3
PKG_RELEASE:=1
PKG_SOURCE:=libhandy-1.8.3.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/libhandy/1.8/
PKG_HASH:=05b497229073ff557f10b326e074c5066f8743a302d4820ab97bcb5cd2dab087
PKG_LICENSE:=LGPL-2.1-or-later
PKG_BUILD_DEPENDS:=
GNOME_TITLE:=GTK3 adaptive widget library
GNOME_DEPENDS:=+libgtk3 +glib2-gir
GNOME_MESON_ARGS:=-Dintrospection=enabled -Dvapi=false -Dgtk_doc=false -Dtests=false -Dexamples=false -Dglade_catalog=disabled

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
