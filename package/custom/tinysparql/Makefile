include $(TOPDIR)/rules.mk

PKG_NAME:=tinysparql
PKG_VERSION:=3.12.0
PKG_RELEASE:=1
PKG_SOURCE:=tinysparql-3.12.0.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/tinysparql/3.12/
PKG_HASH:=40e3e3ae9811ae07a94ac7dfe8259f218679ebb1c9bc98d7ab345b2405926b57
PKG_LICENSE:=LGPL-2.1-or-later
PKG_BUILD_DEPENDS:=
GNOME_TITLE:=SPARQL semantic desktop library
GNOME_DEPENDS:=+glib2-gir +json-glib +libxml2 +libsqlite3 +icu +libsoup3
GNOME_MESON_ARGS:=-Ddocs=false -Dman=false -Dintrospection=enabled -Dvapi=disabled -Dtests=false -Dstemmer=disabled -Dunicode_support=icu -Davahi=disabled -Dbash_completion=false -Dsystemd_user_services=true

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
