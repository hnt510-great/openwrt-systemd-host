include $(TOPDIR)/rules.mk

PKG_NAME:=libgweather
PKG_VERSION:=4.6.0
PKG_RELEASE:=1
PKG_SOURCE:=libgweather-4.6.0.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/libgweather/4.6/
PKG_HASH:=7f5d0e8c9685ef2ff46c2f3a57cae48d7bf3540b2d83921f889ef28e6a876788
PKG_LICENSE:=LGPL-2.1-or-later
PKG_BUILD_DEPENDS:=
GNOME_TITLE:=GNOME weather library
GNOME_DEPENDS:=+gweather-locations +glib2-gir +libsoup3 +geocode-glib +libxml2 +zoneinfo-core
GNOME_MESON_ARGS:=-Denable_vala=false -Dgtk_doc=false -Dintrospection=true -Dtests=false

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
