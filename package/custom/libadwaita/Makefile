include $(TOPDIR)/rules.mk

PKG_NAME:=libadwaita
PKG_VERSION:=1.10.0
PKG_RELEASE:=1
PKG_SOURCE:=libadwaita-1.10.0.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/libadwaita/1.10/
PKG_HASH:=b1bf56239269d101a6391ad4553c910eff9cc6170b803916405477ef60a66c84
PKG_LICENSE:=LGPL-2.1-or-later
PKG_BUILD_DEPENDS:=
GNOME_TITLE:=GNOME adaptive widgets
GNOME_DEPENDS:=+gtk4 +fribidi
GNOME_MESON_ARGS:=-Dintrospection=enabled -Dvapi=false -Ddocumentation=false -Dgtk_doc=false -Dtests=false -Dexamples=false

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
