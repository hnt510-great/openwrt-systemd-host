include $(TOPDIR)/rules.mk

PKG_NAME:=libXi
PKG_VERSION:=1.8.2
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/lib/
PKG_HASH:=d0e0555e53d6e2114eabfa44226ba162d2708501a25e18d99cfb35c094c6c104

XORG_DEPENDS:=+libX11 +libXext +libXfixes

include ../xorg-client.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
