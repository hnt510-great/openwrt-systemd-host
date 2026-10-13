include $(TOPDIR)/rules.mk

PKG_NAME:=libxkbfile
PKG_VERSION:=1.2.0
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/lib/
PKG_HASH:=7f71884e5faf56fb0e823f3848599cf9b5a9afce51c90982baeb64f635233ebf

XORG_DEPENDS:=+libX11

include ../xorg-meson.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
