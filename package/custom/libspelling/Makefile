include $(TOPDIR)/rules.mk

PKG_NAME:=libspelling
PKG_VERSION:=0.4.11
PKG_RELEASE:=1
PKG_SOURCE:=libspelling-0.4.11.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/libspelling/0.4/
PKG_HASH:=52e53ec3fba0f604cfd0931e26af7f7241a0d4f0208dd5574f43b3589f6d28b2
PKG_LICENSE:=LGPL-2.1-or-later
PKG_LICENSE_FILES:=COPYING
PKG_BUILD_DEPENDS:=
GNOME_TITLE:=GTK4 and GtkSourceView spellchecking library
GNOME_DEPENDS:=+glib2-gir +gtk4 +gtksourceview +icu
GNOME_MESON_ARGS:=-Denchant=disabled -Dsysprof=false -Ddocs=false -Dvapi=false -Dintrospection=enabled -Dinstall-static=false

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
