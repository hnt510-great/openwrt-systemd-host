include $(TOPDIR)/rules.mk

PKG_NAME:=libXfixes
PKG_VERSION:=6.0.2
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/lib/
PKG_HASH:=39f115d72d9c5f8111e4684164d3d68cc1fd21f9b27ff2401b08fddfc0f409ba

XORG_DEPENDS:=+libX11

include ../xorg-client.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
