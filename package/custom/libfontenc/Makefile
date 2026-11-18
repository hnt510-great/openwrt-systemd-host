include $(TOPDIR)/rules.mk

PKG_NAME:=libfontenc
PKG_VERSION:=1.1.10
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/lib/
PKG_HASH:=daa186a49e3cc2b6fc585ca09971351e6f010f618abc6a164eda82e42e4aa4d6

XORG_DEPENDS:=+zlib

include ../xorg-meson.mk

MESON_ARGS += -Dwith-fontrootdir=/usr/share/fonts/X11

$(eval $(call BuildPackage,$(PKG_NAME)))
