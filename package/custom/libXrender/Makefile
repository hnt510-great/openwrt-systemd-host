include $(TOPDIR)/rules.mk

PKG_NAME:=libXrender
PKG_VERSION:=0.9.12
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/lib/
PKG_HASH:=b832128da48b39c8d608224481743403ad1691bf4e554e4be9c174df171d1b97

XORG_DEPENDS:=+libX11

include ../xorg-client.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
