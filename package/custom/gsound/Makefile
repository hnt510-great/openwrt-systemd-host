include $(TOPDIR)/rules.mk

PKG_NAME:=gsound
PKG_VERSION:=1.0.3
PKG_RELEASE:=1
PKG_SOURCE:=gsound-1.0.3.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/gsound/1.0/
PKG_HASH:=ca2d039e1ebd148647017a7f548862350bc9af01986d39f10cfdc8e95f07881a
PKG_LICENSE:=LGPL-2.1-or-later
GNOME_TITLE:=GObject sound event library
GNOME_DEPENDS:=+glib2-gir +libcanberra
GNOME_MESON_ARGS:=-Dintrospection=true -Denable_vala=false -Dgtk_doc=false

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
