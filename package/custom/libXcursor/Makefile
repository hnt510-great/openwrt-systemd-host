include $(TOPDIR)/rules.mk

PKG_NAME:=libXcursor
PKG_VERSION:=1.2.3
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/lib/
PKG_HASH:=fde9402dd4cfe79da71e2d96bb980afc5e6ff4f8a7d74c159e1966afb2b2c2c0

XORG_DEPENDS:=+libX11 +libXrender +libXfixes

include ../xorg-client.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
