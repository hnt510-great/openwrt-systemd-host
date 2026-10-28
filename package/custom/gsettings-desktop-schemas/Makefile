include $(TOPDIR)/rules.mk

PKG_NAME:=gsettings-desktop-schemas
PKG_VERSION:=51.0
PKG_RELEASE:=1
PKG_SOURCE:=gsettings-desktop-schemas-51.0.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/gsettings-desktop-schemas/51/
PKG_HASH:=1e2419a5f21d26c324b28ae1c00e29e9175e8b596fff385a04c2172b36652226
PKG_LICENSE:=LGPL-2.1-or-later
PKG_BUILD_DEPENDS:=
GNOME_TITLE:=GNOME desktop settings schemas
GNOME_DEPENDS:=+glib2-gir
GNOME_MESON_ARGS:=-Dintrospection=true

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
