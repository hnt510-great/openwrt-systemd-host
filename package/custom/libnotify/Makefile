include $(TOPDIR)/rules.mk

PKG_NAME:=libnotify
PKG_VERSION:=0.8.9
PKG_RELEASE:=1
PKG_SOURCE:=libnotify-0.8.9.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/libnotify/0.8/
PKG_HASH:=c906bb084027ea512f94a60fbfc0cc8d4f17e4b4d525bed370d07a6d8714c923
PKG_LICENSE:=LGPL-2.1-or-later
PKG_BUILD_DEPENDS:=
GNOME_TITLE:=Desktop notification client library
GNOME_DEPENDS:=+glib2-gir +libgdk-pixbuf
GNOME_MESON_ARGS:=-Dintrospection=enabled -Dtests=false -Dman=false -Dgtk_doc=false -Ddocbook_docs=disabled

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
