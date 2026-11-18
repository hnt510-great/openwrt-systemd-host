include $(TOPDIR)/rules.mk

PKG_NAME:=libXfont2
PKG_VERSION:=2.0.10
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/lib/
PKG_HASH:=cef1f4ad9cd69f439bb1ac484bdc8f9d7f8e70215b92d8ca86b96e31513e5f9c

XORG_DEPENDS:=+libfontenc +libfreetype +zlib
PKG_BUILD_DEPENDS:=xtrans

include ../xorg-client.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
