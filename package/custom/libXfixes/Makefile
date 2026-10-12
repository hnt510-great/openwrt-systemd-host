include $(TOPDIR)/rules.mk

PKG_NAME:=libXfixes
PKG_VERSION:=6.0.1
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/lib/
PKG_HASH:=b695f93cd2499421ab02d22744458e650ccc88c1d4c8130d60200213abc02d58

XORG_DEPENDS:=+libX11

include ../xorg-client.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
