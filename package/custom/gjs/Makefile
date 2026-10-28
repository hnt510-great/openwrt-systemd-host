include $(TOPDIR)/rules.mk

PKG_NAME:=gjs
PKG_VERSION:=1.90.1
PKG_RELEASE:=1
PKG_SOURCE:=gjs-1.90.1.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/gjs/1.90/
PKG_HASH:=05ceaa80f48e3782e5c44938572fad863e02b8c4a6c55657a99aa81db8ce9efa
PKG_LICENSE:=LGPL-2.1-or-later
PKG_BUILD_DEPENDS:=
GNOME_TITLE:=GNOME JavaScript runtime
GNOME_DEPENDS:=+mozjs140 +icu-full-data +glib2-gir +libffi +libcairo +libstdcpp
GNOME_MESON_ARGS:=-Dreadline=disabled -Dprofiler=disabled -Dinstalled_tests=false

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
