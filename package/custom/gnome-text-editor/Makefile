include $(TOPDIR)/rules.mk

PKG_NAME:=gnome-text-editor
PKG_VERSION:=51.0
PKG_RELEASE:=1
PKG_SOURCE:=gnome-text-editor-51.0.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/gnome-text-editor/51/
PKG_HASH:=2b76e6da1506346c54b36ba1a3aeedcd28f4cb7d6a8793d217f209456c92dd4c
PKG_LICENSE:=GPL-3.0-or-later
PKG_LICENSE_FILES:=COPYING
PKG_BUILD_DEPENDS:=
GNOME_TITLE:=GNOME Text Editor
GNOME_DEPENDS:=+glib2 +gtk4 +gtksourceview +libadwaita +libspelling +icu
GNOME_MESON_ARGS:=-Deditorconfig=disabled -Ddevelopment=false

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
