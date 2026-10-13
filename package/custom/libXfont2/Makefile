include $(TOPDIR)/rules.mk

PKG_NAME:=libXfont2
PKG_VERSION:=2.0.9
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/lib/
PKG_HASH:=f042a370666815e7b941e9b7019024755bd1c6c2954afbfa515af378251799e2

XORG_DEPENDS:=+libfontenc +libfreetype +zlib
PKG_BUILD_DEPENDS:=xtrans

include ../xorg-client.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
