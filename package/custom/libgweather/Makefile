include $(TOPDIR)/rules.mk

PKG_NAME:=libgweather
PKG_VERSION:=4.4.4
PKG_RELEASE:=2
PKG_SOURCE:=libgweather-4.4.4.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/libgweather/4.4/
PKG_HASH:=7017677753cdf7d1fdc355e4bfcdb1eba8369793a8df24d241427a939cbf4283
PKG_LICENSE:=LGPL-2.1-or-later
PKG_BUILD_DEPENDS:=
GNOME_TITLE:=GNOME weather library
GNOME_DEPENDS:=+glib2-gir +libsoup3 +geocode-glib +libxml2 +zoneinfo-core
GNOME_MESON_ARGS:=-Denable_vala=false -Dgtk_doc=false -Dintrospection=true -Dtests=false

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
