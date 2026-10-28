include $(TOPDIR)/rules.mk

PKG_NAME:=gnome-autoar
PKG_VERSION:=0.4.5
PKG_RELEASE:=1
PKG_SOURCE:=gnome-autoar-0.4.5.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/gnome-autoar/0.4/
PKG_HASH:=838c5306fc38bfaa2f23abe24262f4bf15771e3303fb5dcb74f5b9c7a615dabe
PKG_LICENSE:=LGPL-2.1-or-later
PKG_BUILD_DEPENDS:=
GNOME_TITLE:=GNOME archive library
GNOME_DEPENDS:=+glib2-gir +libarchive +libgtk3
GNOME_MESON_ARGS:=-Dgtk=true -Dintrospection=enabled -Dvapi=false -Dgtk_doc=false -Dtests=false

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
