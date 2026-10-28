include $(TOPDIR)/rules.mk

PKG_NAME:=geoclue
PKG_VERSION:=2.8.2
PKG_RELEASE:=1
PKG_SOURCE:=geoclue-2.8.2.tar.gz
PKG_SOURCE_URL:=https://gitlab.freedesktop.org/geoclue/geoclue/-/archive/2.8.2/
PKG_HASH:=5435f7d48105fe89a4259f807658281e854881267254bcd4eeac6e26c222055b
PKG_LICENSE:=LGPL-2.1-or-later
PKG_BUILD_DEPENDS:=
GNOME_TITLE:=GNOME location convenience library
GNOME_DEPENDS:=+glib2-gir
GNOME_MESON_ARGS:=-Denable-backend=false -Dlibgeoclue=true -Dintrospection=true -Dvapi=false -Dgtk-doc=false -Ddemo-agent=false

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
