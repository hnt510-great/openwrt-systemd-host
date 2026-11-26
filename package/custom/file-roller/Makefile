include $(TOPDIR)/rules.mk

PKG_NAME:=file-roller
PKG_VERSION:=44.8
PKG_RELEASE:=1
PKG_SOURCE:=file-roller-44.8.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/file-roller/44/
PKG_HASH:=40a560efe9fff957376fd92358580839acc79e2065addbf8491f7a14438c5755
PKG_LICENSE:=GPL-2.0-or-later
PKG_LICENSE_FILES:=COPYING
PKG_BUILD_DEPENDS:=
GNOME_TITLE:=GNOME Archive Manager
GNOME_DEPENDS:=+glib2 +gtk4 +libadwaita +libportal +json-glib +libarchive +nautilus +cpio
GNOME_MESON_ARGS:=-Dpackagekit=false -Dnautilus-actions=enabled -Dnotification=enabled -Dlibarchive=enabled -Duse_native_appchooser=true -Dcpio=/usr/bin/cpio -Dintrospection=disabled -Dapi_docs=disabled

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
