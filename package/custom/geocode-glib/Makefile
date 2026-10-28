include $(TOPDIR)/rules.mk

PKG_NAME:=geocode-glib
PKG_VERSION:=3.26.4
PKG_RELEASE:=1
PKG_SOURCE:=geocode-glib-3.26.4.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/geocode-glib/3.26/
PKG_HASH:=2d9a6826d158470449a173871221596da0f83ebdcff98b90c7049089056a37aa
PKG_LICENSE:=LGPL-2.1-or-later
PKG_BUILD_DEPENDS:=
GNOME_TITLE:=Geocoding and reverse geocoding library
GNOME_DEPENDS:=+glib2-gir +libsoup3 +json-glib
GNOME_MESON_ARGS:=-Dsoup2=false -Denable-gtk-doc=false -Denable-introspection=true -Denable-installed-tests=false

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
