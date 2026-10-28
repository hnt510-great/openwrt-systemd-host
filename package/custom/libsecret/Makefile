include $(TOPDIR)/rules.mk

PKG_NAME:=libsecret
PKG_VERSION:=0.21.8.2
PKG_RELEASE:=1
PKG_SOURCE:=libsecret-0.21.8.2.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/libsecret/0.21/
PKG_HASH:=142948339c5b971d8f6a8c7099521f6fd319b6fe73d2694b4e6d3310ed28b6e6
PKG_LICENSE:=LGPL-2.1-or-later
PKG_BUILD_DEPENDS:=
GNOME_TITLE:=Secret Service client library
GNOME_DEPENDS:=+glib2-gir +libgcrypt
GNOME_MESON_ARGS:=-Dintrospection=true -Dvapi=false -Dgtk_doc=false -Dmanpage=false -Dbash_completion=disabled -Dtpm2=false -Dpam=false

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
