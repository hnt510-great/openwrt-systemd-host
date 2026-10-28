include $(TOPDIR)/rules.mk

PKG_NAME:=libgusb
PKG_VERSION:=0.4.9
PKG_RELEASE:=1
PKG_SOURCE:=libgusb-0.4.9.tar.xz
PKG_SOURCE_URL:=https://github.com/hughsie/libgusb/releases/download/0.4.9/
PKG_HASH:=9df5ef301d6a4b361002aa52cce1165a87a89744055879bdbab31e7e86f1e846
PKG_LICENSE:=LGPL-2.1-or-later
PKG_BUILD_DEPENDS:=
GNOME_TITLE:=libgusb
GNOME_DEPENDS:=+glib2-gir +libusb-1.0 +json-glib
GNOME_MESON_ARGS:=-Dintrospection=true -Dvapi=false -Dtests=false -Ddocs=false -Dumockdev=disabled

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
