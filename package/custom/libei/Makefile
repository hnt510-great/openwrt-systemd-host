include $(TOPDIR)/rules.mk

PKG_NAME:=libei
PKG_VERSION:=1.6.0
PKG_RELEASE:=1
PKG_SOURCE:=libei-1.6.0.tar.gz
PKG_SOURCE_URL:=https://gitlab.freedesktop.org/libinput/libei/-/archive/1.6.0/
PKG_HASH:=81b4b967f0e5938492434a04f7ea2e6c6d96d3e6c44700bc691821f82281e602
PKG_LICENSE:=LGPL-2.1-or-later
PKG_BUILD_DEPENDS:=python3/host
GNOME_TITLE:=libei
GNOME_DEPENDS:=+libevdev +libxkbcommon +libinput +libsystemd
GNOME_MESON_ARGS:=-Dlibei=enabled -Dlibeis=enabled -Dliboeffis=enabled -Dtests=disabled -Ddocumentation=[]

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
