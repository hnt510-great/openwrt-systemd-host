include $(TOPDIR)/rules.mk

PKG_NAME:=libfontenc
PKG_VERSION:=1.1.9
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/lib/
PKG_HASH:=9d8392705cb10803d5fe1d27d236cbab3f664e26841ce01916bbbe430cf273e2

XORG_DEPENDS:=+zlib

include ../xorg-meson.mk

MESON_ARGS += -Dwith-fontrootdir=/usr/share/fonts/X11

$(eval $(call BuildPackage,$(PKG_NAME)))
